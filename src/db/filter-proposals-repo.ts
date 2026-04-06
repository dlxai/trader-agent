import type Database from "better-sqlite3";

export type ProposalStatus = "pending" | "approved" | "rejected";

export interface FilterProposalRow {
  proposal_id: number;
  created_at: number;
  field: string;
  old_value: string;
  proposed_value: string;
  rationale: string;
  sample_count: number;
  expected_delta_winrate: number | null;
  status: ProposalStatus;
  reviewed_at: number | null;
}

export type NewProposal = Omit<
  FilterProposalRow,
  "proposal_id" | "created_at" | "status" | "reviewed_at"
>;

export interface FilterProposalsRepo {
  create(proposal: NewProposal): number;
  getById(id: number): FilterProposalRow | null;
  listPending(): FilterProposalRow[];
  review(id: number, newStatus: "approved" | "rejected"): void;
}

export function createFilterProposalsRepo(db: Database.Database): FilterProposalsRepo {
  const insertStmt = db.prepare(`
    INSERT INTO filter_proposals
      (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate)
    VALUES
      (@created_at, @field, @old_value, @proposed_value, @rationale, @sample_count, @expected_delta_winrate)
  `);

  const getByIdStmt = db.prepare(`
    SELECT proposal_id, created_at, field, old_value, proposed_value, rationale,
           sample_count, expected_delta_winrate, status, reviewed_at
    FROM filter_proposals
    WHERE proposal_id = ?
  `);

  const listPendingStmt = db.prepare(`
    SELECT proposal_id, created_at, field, old_value, proposed_value, rationale,
           sample_count, expected_delta_winrate, status, reviewed_at
    FROM filter_proposals
    WHERE status = 'pending'
    ORDER BY created_at DESC
  `);

  const reviewStmt = db.prepare(`
    UPDATE filter_proposals
    SET status = @status, reviewed_at = @reviewed_at
    WHERE proposal_id = @proposal_id
  `);

  return {
    create(proposal) {
      const result = insertStmt.run({
        created_at: Date.now(),
        field: proposal.field,
        old_value: proposal.old_value,
        proposed_value: proposal.proposed_value,
        rationale: proposal.rationale,
        sample_count: proposal.sample_count,
        expected_delta_winrate: proposal.expected_delta_winrate ?? null,
      });
      return result.lastInsertRowid as number;
    },

    getById(id) {
      return (getByIdStmt.get(id) as FilterProposalRow | undefined) ?? null;
    },

    listPending() {
      return listPendingStmt.all() as FilterProposalRow[];
    },

    review(id, newStatus) {
      const result = reviewStmt.run({
        proposal_id: id,
        status: newStatus,
        reviewed_at: Date.now(),
      });
      if (result.changes !== 1) {
        throw new Error(`review: expected 1 row updated, got ${result.changes} for proposal_id ${id}`);
      }
    },
  };
}
