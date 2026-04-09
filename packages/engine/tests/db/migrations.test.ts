import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations, currentSchemaVersion } from "../../src/db/migrations.js";

describe("runMigrations", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
  });

  it("creates all required tables on fresh db", () => {
    runMigrations(db);
    const tables = db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
      .all()
      .map((r: any) => r.name);
    expect(tables).toContain("signal_log");
    expect(tables).toContain("strategy_performance");
    expect(tables).toContain("filter_config");
    expect(tables).toContain("filter_proposals");
    expect(tables).toContain("strategy_kill_switch");
    expect(tables).toContain("portfolio_state");
    expect(tables).toContain("schema_version");
  });

  it("records current schema version after migration", () => {
    runMigrations(db);
    expect(currentSchemaVersion(db)).toBe(3);
  });

  it("is idempotent — second run does nothing", () => {
    runMigrations(db);
    const firstVersion = currentSchemaVersion(db);
    runMigrations(db);
    expect(currentSchemaVersion(db)).toBe(firstVersion);
  });
});
