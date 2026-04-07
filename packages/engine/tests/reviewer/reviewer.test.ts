import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createStrategyPerformanceRepo } from "../../src/db/strategy-performance-repo.js";
import { runReviewer } from "../../src/reviewer/reviewer.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("runReviewer integration", () => {
  let db: Database.Database;
  let tempHome: string;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    tempHome = join(tmpdir(), `polymarket-trader-test-${Date.now()}-${Math.random()}`);
    process.env.POLYMARKET_TRADER_HOME = tempHome;
  });

  it("produces a report file when there are no trades", async () => {
    const result = await runReviewer({
      db,
      config: DEFAULT_CONFIG,
      signalRepo: createSignalLogRepo(db),
      strategyPerfRepo: createStrategyPerformanceRepo(db),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
    expect(result.bucketCount).toBe(0);
    expect(result.killSwitches).toBe(0);
    expect(existsSync(result.reportPath)).toBe(true);
    const md = readFileSync(result.reportPath, "utf-8");
    expect(md).toContain("Polymarket Reviewer Report");
    rmSync(tempHome, { recursive: true, force: true });
  });
});
