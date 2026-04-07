import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createFilterConfigRepo } from "../../src/db/filter-config-repo.js";

describe("filterConfigRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createFilterConfigRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createFilterConfigRepo(db);
  });

  it("returns null for missing key", () => {
    expect(repo.get("nonexistent")).toBeNull();
  });

  it("upserts a value and reads it back with source", () => {
    repo.set("min_net_flow_1m", "3500", "default");
    const entry = repo.get("min_net_flow_1m");
    expect(entry).not.toBeNull();
    expect(entry?.value).toBe("3500");
    expect(entry?.source).toBe("default");
  });

  it("upserting same key replaces the value and updates source", () => {
    repo.set("threshold", "100", "default");
    repo.set("threshold", "200", "proposal:42");
    const entry = repo.get("threshold");
    expect(entry?.value).toBe("200");
    expect(entry?.source).toBe("proposal:42");
  });

  it("listAll returns every entry", () => {
    repo.set("a", "1", "default");
    repo.set("b", "2", "default");
    const all = repo.listAll();
    expect(all).toHaveLength(2);
    expect(all.map((e) => e.key).sort()).toEqual(["a", "b"]);
  });
});
