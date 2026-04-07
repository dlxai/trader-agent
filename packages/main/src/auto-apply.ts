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
