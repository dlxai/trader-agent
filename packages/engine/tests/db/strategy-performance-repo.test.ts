import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import {
  createStrategyPerformanceRepo,
  type StrategyPerformanceRow,
} from "../../src/db/strategy-performance-repo.js";

describe("strategyPerformanceRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createStrategyPerformanceRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createStrategyPerformanceRepo(db);
  });

  function sample(bucket: number, win_rate: number): StrategyPerformanceRow {
    return {
      price_bucket: bucket,
      window: "7d",
      trade_count: 10,
      win_count: Math.round(win_rate * 10),
      win_rate,
      total_pnl_net_usdc: 50,
      last_updated: 1_700_000_000_000,
    };
  }

  it("upserts a new row and reads it back", () => {
    repo.upsert(sample(0.55, 0.6));
    const row = repo.get(0.55, "7d");
    expect(row).not.toBeNull();
    expect(row?.win_rate).toBe(0.6);
    expect(row?.trade_count).toBe(10);
  });

  it("upsert replaces existing row for same (bucket, window)", () => {
    repo.upsert(sample(0.55, 0.5));
    repo.upsert(sample(0.55, 0.7));
    const row = repo.get(0.55, "7d");
    expect(row?.win_rate).toBe(0.7);
  });

  it("get returns null for unknown bucket+window", () => {
    expect(repo.get(0.55, "7d")).toBeNull();
  });

  it("isolates rows across different windows of same bucket", () => {
    repo.upsert(sample(0.55, 0.6));
    repo.upsert({ ...sample(0.55, 0.65), window: "30d" });
    expect(repo.get(0.55, "7d")?.win_rate).toBe(0.6);
    expect(repo.get(0.55, "30d")?.win_rate).toBe(0.65);
  });

  it("listByWindow returns all buckets for a window, ordered by bucket asc", () => {
    repo.upsert(sample(0.55, 0.5));
    repo.upsert(sample(0.30, 0.7));
    repo.upsert(sample(0.45, 0.55));
    const list = repo.listByWindow("7d");
    expect(list.map((r) => r.price_bucket)).toEqual([0.30, 0.45, 0.55]);
  });
});
