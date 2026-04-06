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
});
