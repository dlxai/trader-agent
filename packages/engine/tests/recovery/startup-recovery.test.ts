import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { performStartupRecovery } from "../../src/recovery/startup-recovery.js";

describe("performStartupRecovery", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
  });

  it("clears daily_halt_triggered flag and re-anchors day_start_equity to current_equity", () => {
    const portfolio = createPortfolioStateRepo(db);
    portfolio.update({
      daily_halt_triggered: true,
      day_start_equity: 10_000,
      current_equity: 9_500,
    });
    const result = performStartupRecovery({
      signalRepo: createSignalLogRepo(db),
      portfolioRepo: portfolio,
      nowMs: Date.now(),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    expect(result.dailyHaltReset).toBe(true);
    expect(portfolio.read().daily_halt_triggered).toBe(false);
    expect(portfolio.read().day_start_equity).toBe(9_500);
  });

  it("clears weekly_halt_triggered flag similarly", () => {
    const portfolio = createPortfolioStateRepo(db);
    portfolio.update({
      weekly_halt_triggered: true,
      week_start_equity: 10_000,
      current_equity: 9_400,
    });
    const result = performStartupRecovery({
      signalRepo: createSignalLogRepo(db),
      portfolioRepo: portfolio,
      nowMs: Date.now(),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    expect(result.weeklyHaltReset).toBe(true);
    expect(portfolio.read().weekly_halt_triggered).toBe(false);
    expect(portfolio.read().week_start_equity).toBe(9_400);
  });

  it("logs count of recovered open positions", () => {
    const signalRepo = createSignalLogRepo(db);
    signalRepo.insert({
      signal_id: "open-1",
      market_id: "m1",
      market_title: "T",
      resolves_at: Date.now() + 3_600_000,
      triggered_at: Date.now(),
      direction: "buy_yes",
      entry_price: 0.5,
      price_bucket: 0.5,
      size_usdc: 100,
      kelly_fraction: 0.1,
      snapshot_volume_1m: 3000,
      snapshot_net_flow_1m: 3000,
      snapshot_unique_traders_1m: 4,
      snapshot_price_move_5m: 0.04,
      snapshot_liquidity: 6000,
      llm_verdict: "real_signal",
      llm_confidence: 0.8,
      llm_reasoning: "",
    });

    const logs: string[] = [];
    const result = performStartupRecovery({
      signalRepo,
      portfolioRepo: createPortfolioStateRepo(db),
      nowMs: Date.now(),
      logger: {
        info: (m) => logs.push(m),
        warn: () => {},
        error: () => {},
      },
    });
    expect(result.openPositionCount).toBe(1);
    expect(logs.some((l) => l.includes("1") && l.toLowerCase().includes("open"))).toBe(true);
  });

  it("returns zero counts when nothing to recover", () => {
    const result = performStartupRecovery({
      signalRepo: createSignalLogRepo(db),
      portfolioRepo: createPortfolioStateRepo(db),
      nowMs: Date.now(),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    expect(result.openPositionCount).toBe(0);
    expect(result.dailyHaltReset).toBe(false);
    expect(result.weeklyHaltReset).toBe(false);
  });
});
