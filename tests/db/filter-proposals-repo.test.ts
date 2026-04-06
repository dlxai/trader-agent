import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import {
  createFilterProposalsRepo,
  type NewProposal,
} from "../../src/db/filter-proposals-repo.js";

function sample(overrides: Partial<NewProposal> = {}): NewProposal {
  return {
    field: "min_net_flow_1m",
    old_value: "3000",
    proposed_value: "3500",
    rationale: "Bucket 0.40-0.60 win rate is 60% over 25 trades; tightening reduces noise.",
    sample_count: 25,
    expected_delta_winrate: 0.05,
    ...overrides,
  };
}

describe("filterProposalsRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createFilterProposalsRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createFilterProposalsRepo(db);
  });

  it("inserts a new proposal with default 'pending' status and returns the id", () => {
    const id = repo.create(sample());
    expect(typeof id).toBe("number");
    expect(id).toBeGreaterThan(0);
    const row = repo.getById(id);
    expect(row).not.toBeNull();
    expect(row?.status).toBe("pending");
    expect(row?.reviewed_at).toBeNull();
    expect(row?.field).toBe("min_net_flow_1m");
  });

  it("getById returns null for unknown id", () => {
    expect(repo.getById(99999)).toBeNull();
  });

  it("listPending returns only pending proposals, newest first", () => {
    const id1 = repo.create(sample({ field: "first" }));
    const id2 = repo.create(sample({ field: "second" }));
    const id3 = repo.create(sample({ field: "third" }));
    repo.review(id2, "approved");
    const pending = repo.listPending();
    expect(pending).toHaveLength(2);
    expect(pending.map((p) => p.field)).toContain("first");
    expect(pending.map((p) => p.field)).toContain("third");
  });

  it("review changes status and sets reviewed_at", () => {
    const id = repo.create(sample());
    repo.review(id, "approved");
    const row = repo.getById(id);
    expect(row?.status).toBe("approved");
    expect(row?.reviewed_at).not.toBeNull();
  });

  it("review throws on unknown proposal id", () => {
    expect(() => repo.review(99999, "approved")).toThrow();
  });

  it("expected_delta_winrate is nullable", () => {
    const id = repo.create({ ...sample(), expected_delta_winrate: null });
    const row = repo.getById(id);
    expect(row?.expected_delta_winrate).toBeNull();
  });
});
