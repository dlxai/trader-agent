import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";

describe("portfolioStateRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createPortfolioStateRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createPortfolioStateRepo(db);
  });

  it("initializes with sensible defaults on first read", () => {
    const state = repo.read();
    expect(state.total_capital).toBe(10_000);
    expect(state.current_equity).toBe(10_000);
    expect(state.peak_equity).toBe(10_000);
    expect(state.current_drawdown).toBe(0);
    expect(state.daily_halt_triggered).toBe(false);
    expect(state.weekly_halt_triggered).toBe(false);
  });

  it("persists updates and reads them back", () => {
    repo.update({ current_equity: 9800, current_drawdown: 0.02 });
    const state = repo.read();
    expect(state.current_equity).toBe(9800);
    expect(state.current_drawdown).toBe(0.02);
    expect(state.total_capital).toBe(10_000);
  });

  it("sets and clears daily halt flag", () => {
    repo.update({ daily_halt_triggered: true });
    expect(repo.read().daily_halt_triggered).toBe(true);
    repo.update({ daily_halt_triggered: false });
    expect(repo.read().daily_halt_triggered).toBe(false);
  });
});
