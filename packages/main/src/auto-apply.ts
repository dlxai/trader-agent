// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DatabaseType = any;

const MIN_SAMPLE_COUNT = 30;
const MIN_DELTA_WINRATE = 0.05;

const LOCKED_FIELDS = new Set([
  "static_dead_zone_min",
  "static_dead_zone_max",
  "kelly_multiplier",
  "max_total_position_usdc",
]);

const LOSS_AFFECTING_FIELDS = new Set([
  "max_single_trade_loss_usdc",
  "stop_loss_pct_normal",
  "stop_loss_pct_late_stage",
  "max_position_usdc",
]);

export interface AutoApplyInput {
  sample_count: number;
  expected_delta_winrate: number | null;
  field: string;
  proposed_value: string;
}

export interface AutoApplyDecision {
  shouldApply: boolean;
  reason: string;
}

export interface ProcessProposalsResult {
  applied: number;
  skipped: number;
}

/**
 * Decides whether a Reviewer-generated filter_proposal can be auto-applied
 * without human approval. The criteria are intentionally strict:
 *
 *   1. Sample size >= 30 trades — small samples are noise
 *   2. Expected win rate improvement >= 5% — small wins not worth LLM hallucination risk
 *   3. Field is not in LOCKED_FIELDS — spec hard limits
 *   4. Field doesn't affect max single trade loss — needs human eyes
 */
export function evaluateAutoApply(input: AutoApplyInput): AutoApplyDecision {
  if (LOCKED_FIELDS.has(input.field)) {
    return {
      shouldApply: false,
      reason: `field ${input.field} is locked (spec hard constraint)`,
    };
  }
  if (LOSS_AFFECTING_FIELDS.has(input.field)) {
    return {
      shouldApply: false,
      reason: `field ${input.field} affects max single trade loss — human review required`,
    };
  }
  if (input.sample_count < MIN_SAMPLE_COUNT) {
    return {
      shouldApply: false,
      reason: `sample size ${input.sample_count} < min ${MIN_SAMPLE_COUNT}`,
    };
  }
  if (
    input.expected_delta_winrate === null ||
    input.expected_delta_winrate < MIN_DELTA_WINRATE
  ) {
    return {
      shouldApply: false,
      reason: `expected delta winrate ${input.expected_delta_winrate ?? "null"} < min ${MIN_DELTA_WINRATE}`,
    };
  }
  return {
    shouldApply: true,
    reason: `${input.sample_count} samples + ${(input.expected_delta_winrate * 100).toFixed(1)}% expected delta — auto-applied`,
  };
}

/**
 * Process all pending filter_proposals and auto-apply high-confidence ones.
 * Called automatically after each Reviewer run.
 */
export function processProposals(db: DatabaseType): ProcessProposalsResult {
  const pending = db
    .prepare(
      "SELECT proposal_id, field, proposed_value, sample_count, expected_delta_winrate FROM filter_proposals WHERE status = 'pending'"
    )
    .all() as Array<{
    proposal_id: number;
    field: string;
    proposed_value: string;
    sample_count: number;
    expected_delta_winrate: number | null;
  }>;

  let applied = 0;
  let skipped = 0;

  for (const p of pending) {
    const decision = evaluateAutoApply({
      sample_count: p.sample_count,
      expected_delta_winrate: p.expected_delta_winrate,
      field: p.field,
      proposed_value: p.proposed_value,
    });

    if (decision.shouldApply) {
      db.transaction(() => {
        // Get old value for audit log
        const oldConfig = db
          .prepare("SELECT value FROM filter_config WHERE key = ?")
          .get(p.field) as { value: string } | undefined;
        const oldValue = oldConfig?.value ?? "";

        // Apply the change
        db.prepare(
          "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
        ).run(p.field, p.proposed_value, Date.now(), `auto-apply:${p.proposal_id}`);

        // Update proposal status
        db.prepare(
          "UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?"
        ).run(Date.now(), p.proposal_id);

        // Write audit log entry
        db.prepare(
          "INSERT INTO filter_config_history (changed_at, key, old_value, new_value, source, proposal_id) VALUES (?, ?, ?, ?, ?, ?)"
        ).run(Date.now(), p.field, oldValue, p.proposed_value, `auto-apply:${p.proposal_id}`, p.proposal_id);
      })();
      applied++;
    } else {
      skipped++;
    }
  }

  return { applied, skipped };
}
