import { VerdictParseError } from "../util/errors.js";
import type { Direction, LlmVerdict } from "../db/types.js";

export interface ParsedVerdict {
  verdict: LlmVerdict;
  direction: Direction;
  confidence: number;
  reasoning: string;
}

const VALID_VERDICTS: LlmVerdict[] = ["real_signal", "noise", "uncertain"];
const VALID_DIRECTIONS: Direction[] = ["buy_yes", "buy_no"];

function extractJson(raw: string): unknown {
  const trimmed = raw.trim();
  const fenceMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1]! : trimmed;
  try {
    return JSON.parse(jsonText);
  } catch (err) {
    throw new VerdictParseError(`Invalid JSON: ${(err as Error).message}`, raw);
  }
}

export function parseVerdict(raw: string): ParsedVerdict {
  const obj = extractJson(raw);
  if (typeof obj !== "object" || obj === null) {
    throw new VerdictParseError("Verdict not an object", raw);
  }
  const o = obj as Record<string, unknown>;

  if (!VALID_VERDICTS.includes(o.verdict as LlmVerdict)) {
    throw new VerdictParseError(`Invalid verdict value: ${String(o.verdict)}`, raw);
  }
  if (!VALID_DIRECTIONS.includes(o.direction as Direction)) {
    throw new VerdictParseError(`Invalid direction: ${String(o.direction)}`, raw);
  }
  const conf = Number(o.confidence);
  if (!Number.isFinite(conf) || conf < 0 || conf > 1) {
    throw new VerdictParseError(`Confidence out of range: ${String(o.confidence)}`, raw);
  }
  const reasoning = typeof o.reasoning === "string" ? o.reasoning : "";

  return {
    verdict: o.verdict as LlmVerdict,
    direction: o.direction as Direction,
    confidence: conf,
    reasoning,
  };
}
