import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "@pmt/engine/db";
import { processProposals } from "../src/auto-apply.js";

describe("processProposals", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
  });

  it("auto-applies a high-confidence proposal", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "min_net_flow_1m", "3000", "3500", "test", 50, 0.08);

    const result = processProposals(db);
    expect(result.applied).toBe(1);
    expect(result.skipped).toBe(0);

    const config = db
      .prepare("SELECT value FROM filter_config WHERE key = ?")
      .get("min_net_flow_1m") as { value: string } | undefined;
    expect(config?.value).toBe("3500");

    const proposal = db
      .prepare("SELECT status FROM filter_proposals WHERE field = ?")
      .get("min_net_flow_1m") as { status: string };
    expect(proposal.status).toBe("approved");
  });

  it("skips low-confidence proposal (small sample)", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "min_net_flow_1m", "3000", "3500", "test", 10, 0.10);

    const result = processProposals(db);
    expect(result.applied).toBe(0);
    expect(result.skipped).toBe(1);

    const proposal = db
      .prepare("SELECT status FROM filter_proposals WHERE field = ?")
      .get("min_net_flow_1m") as { status: string };
    expect(proposal.status).toBe("pending"); // unchanged
  });

  it("skips locked field even with high confidence", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "static_dead_zone_min", "0.60", "0.55", "test", 100, 0.20);

    const result = processProposals(db);
    expect(result.applied).toBe(0);
    expect(result.skipped).toBe(1);
  });
});
