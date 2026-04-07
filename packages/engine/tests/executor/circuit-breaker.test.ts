import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { createCircuitBreaker } from "../../src/executor/circuit-breaker.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";

describe("circuitBreaker", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createPortfolioStateRepo>;
  let breaker: ReturnType<typeof createCircuitBreaker>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createPortfolioStateRepo(db);
    breaker = createCircuitBreaker({ config: DEFAULT_CONFIG, portfolioRepo: repo });
  });

  it("allows new orders when no halt active", () => {
    expect(breaker.canOpenNewPosition()).toBe(true);
  });

  it("triggers daily halt when equity drops 2% below day_start", () => {
    repo.update({ day_start_equity: 10_000, current_equity: 9_799 });
    breaker.evaluate();
    expect(repo.read().daily_halt_triggered).toBe(true);
    expect(breaker.canOpenNewPosition()).toBe(false);
  });

  it("does not trigger daily halt at exactly -1.99%", () => {
    repo.update({ day_start_equity: 10_000, current_equity: 9_801 });
    breaker.evaluate();
    expect(repo.read().daily_halt_triggered).toBe(false);
  });

  it("triggers weekly halt when equity drops 4% below week_start", () => {
    repo.update({ week_start_equity: 10_000, current_equity: 9_590 });
    breaker.evaluate();
    expect(repo.read().weekly_halt_triggered).toBe(true);
    expect(breaker.canOpenNewPosition()).toBe(false);
  });

  it("resets daily halt at day rollover", () => {
    repo.update({ day_start_equity: 10_000, current_equity: 9_700, daily_halt_triggered: true });
    breaker.resetDaily(9_700);
    expect(repo.read().daily_halt_triggered).toBe(false);
    expect(repo.read().day_start_equity).toBe(9_700);
  });

  it("triggers total drawdown emergency stop at 10%", () => {
    repo.update({ peak_equity: 10_000, current_equity: 8_999 });
    expect(breaker.isEmergencyStop()).toBe(true);
  });

  it("resets weekly halt at week rollover", () => {
    repo.update({ week_start_equity: 10_000, current_equity: 9_500, weekly_halt_triggered: true });
    breaker.resetWeekly(9_500);
    expect(repo.read().weekly_halt_triggered).toBe(false);
    expect(repo.read().week_start_equity).toBe(9_500);
  });

  it("evaluate: skips daily loss check when day_start_equity is 0", () => {
    // Explicitly zero out day_start_equity to exercise the false branch on line 24.
    // Also zero week_start_equity so the weekly check doesn't fire instead.
    repo.update({ day_start_equity: 0, week_start_equity: 0, current_equity: 9_500 });
    breaker.evaluate();
    expect(repo.read().daily_halt_triggered).toBe(false);
  });

  it("evaluate: skips weekly loss check when week_start_equity is 0", () => {
    // Explicitly zero out week_start_equity to exercise the false branch on line 31.
    // Set day_start_equity slightly above current so daily check doesn't fire.
    repo.update({ day_start_equity: 0, week_start_equity: 0, current_equity: 9_500 });
    breaker.evaluate();
    expect(repo.read().weekly_halt_triggered).toBe(false);
  });

  it("evaluate: updates peak_equity when current_equity exceeds peak", () => {
    repo.update({ peak_equity: 9_000, current_equity: 10_500 });
    breaker.evaluate();
    expect(repo.read().peak_equity).toBe(10_500);
  });

  it("evaluate: skips drawdown calc when peak_equity is 0", () => {
    // peak_equity=0 means the false branch on line 42
    repo.update({ peak_equity: 0, current_equity: 0 });
    breaker.evaluate();
    // No crash expected; current_drawdown stays as is
    expect(repo.read().peak_equity).toBe(0);
  });

  it("evaluate: does not write patch when nothing changed", () => {
    // Set state such that no condition triggers a patch update
    // day_start_equity=0, week_start_equity=0, peak_equity=0, equity=0
    repo.update({
      day_start_equity: 0,
      week_start_equity: 0,
      peak_equity: 0,
      current_equity: 0,
    });
    // Should not throw — the Object.keys(patch).length === 0 branch
    breaker.evaluate();
    expect(repo.read().current_equity).toBe(0);
  });

  it("canOpenNewPosition: blocks when emergency stop is active", () => {
    repo.update({ peak_equity: 10_000, current_equity: 8_999 });
    // isEmergencyStop() returns true (>= 10% drawdown)
    expect(breaker.canOpenNewPosition()).toBe(false);
  });

  it("isEmergencyStop: returns false when peak_equity is 0", () => {
    repo.update({ peak_equity: 0, current_equity: 0 });
    expect(breaker.isEmergencyStop()).toBe(false);
  });

  it("isEmergencyStop: returns false when drawdown is below threshold", () => {
    repo.update({ peak_equity: 10_000, current_equity: 9_500 });
    expect(breaker.isEmergencyStop()).toBe(false);
  });
});
