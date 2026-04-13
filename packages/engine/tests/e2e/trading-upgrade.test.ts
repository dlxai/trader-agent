import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { createEventBus } from "../../src/bus/events.js";
import { createExecutor } from "../../src/executor/executor.js";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { VerdictEvent } from "../../src/bus/types.js";

function makeVerdict(overrides: Partial<VerdictEvent["trigger"]> = {}): VerdictEvent {
  const now = Date.now();
  return {
    type: "verdict",
    trigger: {
      type: "trigger",
      market_id: "m1",
      market_title: "Test Market",
      resolves_at: now + 7_200_000,
      triggered_at: now,
      direction: "buy_yes",
      snapshot: {
        volume_1m: 5000,
        net_flow_1m: 4000,
        unique_traders_1m: 5,
        price_move_5m: 0.05,
        liquidity: 10000,
        current_mid_price: 0.40,
      },
      ...overrides,
    },
    verdict: "real_signal",
    confidence: 0.80,
    reasoning: "strong flow",
    llm_direction: "buy_yes",
  };
}

describe("trading upgrade integration", () => {
  let db: Database.Database;
  let bus: ReturnType<typeof createEventBus>;
  let exec: ReturnType<typeof createExecutor>;
  let portfolioRepo: ReturnType<typeof createPortfolioStateRepo>;
  let signalRepo: ReturnType<typeof createSignalLogRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    signalRepo = createSignalLogRepo(db);
    portfolioRepo = createPortfolioStateRepo(db);
    bus = createEventBus();
    portfolioRepo.update({
      total_capital: 10_000, current_equity: 10_000,
      day_start_equity: 10_000, week_start_equity: 10_000, peak_equity: 10_000,
    });
    const filler = createPaperFiller({ slippagePct: DEFAULT_CONFIG.paperSlippagePct });
    // Use a higher takeProfitPct so the drawdown guard can fire before A_TP
    const config = { ...DEFAULT_CONFIG, takeProfitPct: 0.25 };
    exec = createExecutor({
      config, bus, signalRepo, portfolioRepo, filler,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
  });

  it("opens position and closes on DRAWDOWN_GUARD", async () => {
    const verdict = makeVerdict();
    const sigId = await exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();
    expect(exec.openPositions()).toHaveLength(1);

    // Simulate price rising to ~20% profit (peak)
    // entry_price ≈ 0.40 * 1.005 = 0.402
    // 0.402 * 1.20 = 0.4824 → ~20% profit
    await exec.onPriceTick("m1", 0.4824, Date.now() + 60_000);
    expect(exec.openPositions()).toHaveLength(1); // still open

    // Now price drops: drawdown from 20% peak
    // Need current profit > 5% (minProfitPct) but drawdown > 40% of peak
    // 20% * 0.55 = 11% → good, >5%
    // drawdown = (20 - 11) / 20 = 45% → > 40%
    // 0.402 * 1.11 = 0.4462
    await exec.onPriceTick("m1", 0.446, Date.now() + 120_000);
    expect(exec.openPositions()).toHaveLength(0); // closed by drawdown guard
  });

  it("new exit reasons are persisted in database", async () => {
    const verdict = makeVerdict();
    await exec.handleVerdict(verdict);
    // Trigger drawdown guard
    await exec.onPriceTick("m1", 0.4824, Date.now() + 60_000);
    await exec.onPriceTick("m1", 0.446, Date.now() + 120_000);

    const rows = db.prepare("SELECT exit_reason FROM signal_log WHERE exit_reason IS NOT NULL").all() as { exit_reason: string }[];
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0].exit_reason).toBe("DRAWDOWN_GUARD");
  });

  it("closePosition accepts new exit reasons", async () => {
    const verdict = makeVerdict();
    await exec.handleVerdict(verdict);
    const pos = exec.openPositions()[0];
    await exec.closePosition(pos, 0.42, Date.now(), "AI_EXIT");
    expect(exec.openPositions()).toHaveLength(0);
  });
});
