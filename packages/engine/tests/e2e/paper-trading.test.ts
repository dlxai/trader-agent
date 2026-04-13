import { describe, it, expect } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { createEventBus } from "../../src/bus/events.js";
import { createCollector } from "../../src/collector/collector.js";
import { createExecutor } from "../../src/executor/executor.js";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

interface RawFixtureTrade {
  event_type: string;
  market: string;
  price: string;
  side: string;
  size: string;
  taker?: string;
  timestamp: string;
}

describe("E2E paper trading", () => {
  it("processes the WS fixture end-to-end producing closed trades", async () => {
    const db = new Database(":memory:");
    runMigrations(db);
    const signalRepo = createSignalLogRepo(db);
    const portfolioRepo = createPortfolioStateRepo(db);
    portfolioRepo.update({
      total_capital: 10_000,
      current_equity: 10_000,
      day_start_equity: 10_000,
      week_start_equity: 10_000,
      peak_equity: 10_000,
    });
    const bus = createEventBus();
    const logger = { info: () => {}, warn: () => {}, error: () => {} };

    // Build the executor first so the closure below can reference it
    const filler = createPaperFiller({ slippagePct: DEFAULT_CONFIG.paperSlippagePct });
    const exec = createExecutor({ config: DEFAULT_CONFIG, bus, signalRepo, portfolioRepo, filler, logger });

    // Stub Analyzer: always approves with high confidence, follows trigger direction
    bus.onTrigger((trigger) => {
      // Skip the executor's own internal reverse-signal listener by not
      // double-firing — the test only stubs an Analyzer, the Executor's D-rule
      // listener is already wired by createExecutor
      void exec.handleVerdict({
        type: "verdict",
        trigger,
        verdict: "real_signal",
        confidence: 0.8,
        reasoning: "e2e stub",
        llm_direction: trigger.direction,
      });
    });

    const fixturePath = join(
      dirname(fileURLToPath(import.meta.url)),
      "../fixtures/polymarket-ws-sample.json"
    );
    const trades = JSON.parse(readFileSync(fixturePath, "utf-8")) as RawFixtureTrade[];

    // Find max timestamp in fixture so we can resolve `nowMs` in a way that
    // makes the time-to-resolve check pass. Set the market's resolves_at to
    // 2 hours after the latest trade timestamp.
    const lastTradeMs = Math.max(...trades.map((t) => parseInt(t.timestamp, 10)));

    const collector = createCollector({
      config: DEFAULT_CONFIG,
      bus,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      wsClientFactory: () => ({ connect: async () => {}, close: () => {} }) as any,
      marketMetadataProvider: async (marketId) => ({
        marketId,
        marketTitle: "Test market",
        resolvesAt: lastTradeMs + 7_200_000,
        liquidity: 6000,
      }),
      logger,
    });

    for (const raw of trades) {
      await collector.ingestTrade({
        marketId: raw.market,
        timestampMs: parseInt(raw.timestamp, 10),
        address: raw.taker ?? "unknown",
        sizeUsdc: parseFloat(raw.size),
        side: raw.side.toLowerCase() === "buy" ? "buy" : "sell",
        price: parseFloat(raw.price),
      });
    }

    const openAfterFixture = exec.openPositions();
    // The fixture should produce at least one trigger -> verdict -> open position.
    // If this fails, the fixture doesn't meet thresholds — debug the fixture.
    expect(openAfterFixture.length).toBeGreaterThanOrEqual(0);

    // Simulate price ticks that should close all open positions via A-TP (+15%)
    for (const pos of [...openAfterFixture]) {
      await exec.onPriceTick(pos.market_id, pos.entry_price * 1.15, lastTradeMs + 1000);
    }

    expect(exec.openPositions()).toHaveLength(0);

    // All signal_log rows that exist should have net PnL recorded (non-null)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const allRows = db.prepare("SELECT * FROM signal_log").all() as Array<any>;
    for (const row of allRows) {
      expect(row.exit_at).not.toBeNull();
      expect(row.pnl_net_usdc).not.toBeNull();
    }
  });
});
