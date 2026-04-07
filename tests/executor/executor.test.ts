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

  it("rejects non-real_signal verdict without opening a position", () => {
    const verdict = makeVerdict();
    verdict.verdict = "noise";
    expect(exec.handleVerdict(verdict)).toBeNull();
    expect(exec.openPositions()).toHaveLength(0);
  });

  it("onPriceTick skips positions on other markets (continue branch)", () => {
    // Open a position on m1, then send a tick for m2 — nothing should close
    const v1 = makeVerdict();
    v1.trigger.market_id = "m1";
    expect(exec.handleVerdict(v1)).not.toBeNull();
    expect(exec.openPositions()).toHaveLength(1);
    // Tick for a different market — should not close the m1 position
    exec.onPriceTick("m2", 0.99, Date.now());
    expect(exec.openPositions()).toHaveLength(1);
  });

  it("onPriceTick does not close when exit conditions not met", () => {
    // Open a position and tick with a price that does not trigger stop-loss or take-profit
    const verdict = makeVerdict();
    const sigId = exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();
    // entry_price ≈ 0.40 * 1.005 = 0.402. A tick at 0.41 is only ~2% profit, below 10% TP.
    exec.onPriceTick("m1", 0.41, Date.now());
    expect(exec.openPositions()).toHaveLength(1);
  });

  it("re-acquires conflict locks for positions loaded from DB on startup", () => {
    // Open a position through exec so it is persisted in the DB
    const verdict = makeVerdict();
    verdict.trigger.market_id = "recovery-market";
    const sigId = exec.handleVerdict(verdict);
    expect(sigId).not.toBeNull();

    // Create a second executor over the same DB — it should recover the open position
    // and re-acquire the lock for "recovery-market" so a duplicate can't be opened.
    const signalRepo2 = createSignalLogRepo(db);
    const exec2 = createExecutor({
      config: DEFAULT_CONFIG,
      bus,
      signalRepo: signalRepo2,
      portfolioRepo,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    expect(exec2.openPositions()).toHaveLength(1);
    // The lock for "recovery-market" should already be held — a duplicate verdict is rejected
    const dup = makeVerdict();
    dup.trigger.market_id = "recovery-market";
    expect(exec2.handleVerdict(dup)).toBeNull();
  });

  it("rejects order when weekly halt is triggered", () => {
    portfolioRepo.update({ weekly_halt_triggered: true });
    expect(exec.handleVerdict(makeVerdict())).toBeNull();
  });

  it("rejects order when total exposure cap is reached", () => {
    // Use a custom executor with a tiny maxTotalPositionUsdc so the first
    // position saturates the cap.
    // At price 0.40: size = floor(min(10000*kelly, 300, 50/0.40)) = floor(125) = 125
    // Set maxTotalPositionUsdc = 100 so 125 + 50 > 100 after first open.
    const db2 = new Database(":memory:");
    runMigrations(db2);
    const signalRepo2 = createSignalLogRepo(db2);
    const portfolioRepo2 = createPortfolioStateRepo(db2);
    portfolioRepo2.update({
      total_capital: 10_000,
      current_equity: 10_000,
      day_start_equity: 10_000,
      week_start_equity: 10_000,
      peak_equity: 10_000,
    });
    const exec2 = createExecutor({
      config: { ...DEFAULT_CONFIG, maxTotalPositionUsdc: 100, minPositionUsdc: 50 },
      bus,
      signalRepo: signalRepo2,
      portfolioRepo: portfolioRepo2,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    // First position: size=floor(50/0.40)=125, but maxPositionUsdc=300 and capital check:
    // 125 >= minPositionUsdc=50, so it opens successfully with size=125
    // After open, totalExposure()=125; 125 + 50 > 100 so next is rejected.
    // BUT 125 > maxTotalPositionUsdc=100 already — the check is BEFORE open.
    // At open time: totalExposure()=0, 0 + 50 <= 100, so first position opens.
    const v1 = makeVerdict();
    v1.trigger.market_id = "cap-m1";
    const id1 = exec2.handleVerdict(v1);
    expect(id1).not.toBeNull();
    // Now totalExposure=125; 125 + 50=175 > 100 => rejected
    const v2 = makeVerdict();
    v2.trigger.market_id = "cap-m2";
    expect(exec2.handleVerdict(v2)).toBeNull();
  });

  it("rejects order when max open positions limit is reached", () => {
    // Use a custom executor with maxOpenPositions=1 to hit the limit quickly.
    const db3 = new Database(":memory:");
    runMigrations(db3);
    const signalRepo3 = createSignalLogRepo(db3);
    const portfolioRepo3 = createPortfolioStateRepo(db3);
    portfolioRepo3.update({
      total_capital: 10_000,
      current_equity: 10_000,
      day_start_equity: 10_000,
      week_start_equity: 10_000,
      peak_equity: 10_000,
    });
    const exec3 = createExecutor({
      config: { ...DEFAULT_CONFIG, maxOpenPositions: 1, maxTotalPositionUsdc: 10_000 },
      bus,
      signalRepo: signalRepo3,
      portfolioRepo: portfolioRepo3,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    const v1 = makeVerdict();
    v1.trigger.market_id = "max-m1";
    expect(exec3.handleVerdict(v1)).not.toBeNull();
    const v2 = makeVerdict();
    v2.trigger.market_id = "max-m2";
    expect(exec3.handleVerdict(v2)).toBeNull();
  });
});
