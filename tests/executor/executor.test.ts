import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { createEventBus } from "../../src/bus/events.js";
import { createExecutor } from "../../src/executor/executor.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { VerdictEvent } from "../../src/bus/types.js";

function makeVerdict(): VerdictEvent {
  const now = Date.now();
  return {
    type: "verdict",
    trigger: {
      type: "trigger",
      market_id: "m1",
      market_title: "Test",
      resolves_at: now + 7_200_000,
      triggered_at: now,
      direction: "buy_yes",
      snapshot: {
        volume_1m: 3500,
        net_flow_1m: 3200,
        unique_traders_1m: 4,
        price_move_5m: 0.04,
        liquidity: 6000,
        current_mid_price: 0.40,
      },
    },
    verdict: "real_signal",
    confidence: 0.80,
    reasoning: "strong flow",
    llm_direction: "buy_yes",
  };
}

describe("executor", () => {
  let db: Database.Database;
  let bus: ReturnType<typeof createEventBus>;
  let exec: ReturnType<typeof createExecutor>;
  let portfolioRepo: ReturnType<typeof createPortfolioStateRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    const signalRepo = createSignalLogRepo(db);
    portfolioRepo = createPortfolioStateRepo(db);
    bus = createEventBus();
    portfolioRepo.update({
      total_capital: 10_000,
      current_equity: 10_000,
      day_start_equity: 10_000,
      week_start_equity: 10_000,
      peak_equity: 10_000,
    });
    exec = createExecutor({
      config: DEFAULT_CONFIG,
      bus,
      signalRepo,
      portfolioRepo,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
  });

  it("executes an order when conditions are met", () => {
    const verdict = makeVerdict();
    const sigId = exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();
    expect(exec.openPositions()).toHaveLength(1);
  });

  it("rejects a second order for the same market (conflict lock)", () => {
    const verdict = makeVerdict();
    const id1 = exec.handleVerdict(verdict);
    const id2 = exec.handleVerdict(verdict);
    expect(id1).not.toBeNull();
    expect(id2).toBeNull();
    expect(exec.openPositions()).toHaveLength(1);
  });

  it("rejects order when daily halt is triggered", () => {
    portfolioRepo.update({ daily_halt_triggered: true });
    expect(exec.handleVerdict(makeVerdict())).toBeNull();
  });

  it("rejects order when Kelly returns 0 (dead zone)", () => {
    const verdict = makeVerdict();
    verdict.trigger.snapshot.current_mid_price = 0.72;
    expect(exec.handleVerdict(verdict)).toBeNull();
  });

  // Note: entry mid price is 0.40, fill price = 0.40 * 1.005 = 0.402.
  // takeProfitPct = 0.10, so we need (tick - 0.402) / 0.402 >= 0.10 → tick >= 0.4422.
  // Using 0.45 gives profitDelta ≈ 0.119 which exceeds the 10% threshold.
  it("processes tick, triggers A-TP at +10%, closes position", () => {
    const verdict = makeVerdict();
    const sigId = exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();
    exec.onPriceTick("m1", 0.45, Date.now());
    expect(exec.openPositions()).toHaveLength(0);
  });

  it("handles reverse signal by publishing exit", () => {
    const verdict = makeVerdict();
    const sigId = exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();
    bus.publishTrigger({
      ...verdict.trigger,
      direction: "buy_no",
      triggered_at: Date.now() + 60_000,
    });
    expect(exec.openPositions()).toHaveLength(0);
  });
});
