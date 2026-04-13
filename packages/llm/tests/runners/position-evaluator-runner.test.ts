import { describe, it, expect } from "vitest";
import { parsePositionEvaluation } from "../../src/runners/position-evaluator-runner.js";

describe("parsePositionEvaluation", () => {
  it("parses a valid close action", () => {
    const json = JSON.stringify({
      positions: [
        {
          signal_id: "sig-001",
          action: "close",
          reasoning: "Opposing flow detected, likely new information.",
        },
      ],
    });
    const result = parsePositionEvaluation(json);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
    expect(result!.positions[0].signal_id).toBe("sig-001");
    expect(result!.positions[0].action).toBe("close");
    expect(result!.positions[0].reasoning).toBe("Opposing flow detected, likely new information.");
    expect(result!.positions[0].new_stop_loss_pct).toBeUndefined();
    expect(result!.positions[0].new_take_profit_pct).toBeUndefined();
  });

  it("parses a valid adjust_sl_tp action with new_stop_loss_pct and new_take_profit_pct", () => {
    const json = JSON.stringify({
      positions: [
        {
          signal_id: "sig-002",
          action: "adjust_sl_tp",
          new_stop_loss_pct: 0.03,
          new_take_profit_pct: 0.15,
          reasoning: "Position profitable but starting to retreat, tightening exits.",
        },
      ],
    });
    const result = parsePositionEvaluation(json);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
    expect(result!.positions[0].signal_id).toBe("sig-002");
    expect(result!.positions[0].action).toBe("adjust_sl_tp");
    expect(result!.positions[0].new_stop_loss_pct).toBe(0.03);
    expect(result!.positions[0].new_take_profit_pct).toBe(0.15);
    expect(result!.positions[0].reasoning).toBe("Position profitable but starting to retreat, tightening exits.");
  });

  it("parses a valid hold action", () => {
    const json = JSON.stringify({
      positions: [
        {
          signal_id: "sig-003",
          action: "hold",
          reasoning: "Price moving favorably with sustained inflow.",
        },
      ],
    });
    const result = parsePositionEvaluation(json);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
    expect(result!.positions[0].action).toBe("hold");
    expect(result!.positions[0].signal_id).toBe("sig-003");
  });

  it("returns null for invalid JSON", () => {
    const result = parsePositionEvaluation("this is not json at all");
    expect(result).toBeNull();
  });

  it("filters out invalid actions and returns only valid ones", () => {
    const json = JSON.stringify({
      positions: [
        {
          signal_id: "sig-valid",
          action: "hold",
          reasoning: "Valid position.",
        },
        {
          signal_id: "sig-bad",
          action: "unknown_action",
          reasoning: "Invalid action.",
        },
        {
          signal_id: "sig-no-id",
          action: "close",
          // signal_id is missing (not a string)
        },
      ],
    });
    // Override signal_id for the third entry to be non-string
    const parsed = JSON.parse(json);
    parsed.positions[2].signal_id = 12345;
    const result = parsePositionEvaluation(JSON.stringify(parsed));
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
    expect(result!.positions[0].signal_id).toBe("sig-valid");
  });

  it("returns empty positions array when all actions are invalid", () => {
    const json = JSON.stringify({
      positions: [
        { signal_id: "sig-x", action: "buy", reasoning: "bad action" },
        { signal_id: "sig-y", action: "sell", reasoning: "also bad" },
      ],
    });
    const result = parsePositionEvaluation(json);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(0);
  });

  it("handles markdown code fence wrapping", () => {
    const inner = JSON.stringify({
      positions: [
        {
          signal_id: "sig-fenced",
          action: "close",
          reasoning: "Market near expiry with unclear direction.",
        },
      ],
    });
    const fenced = "```json\n" + inner + "\n```";
    const result = parsePositionEvaluation(fenced);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
    expect(result!.positions[0].signal_id).toBe("sig-fenced");
    expect(result!.positions[0].action).toBe("close");
  });

  it("handles plain markdown fence without language tag", () => {
    const inner = JSON.stringify({
      positions: [{ signal_id: "sig-plain", action: "hold", reasoning: "All good." }],
    });
    const fenced = "```\n" + inner + "\n```";
    const result = parsePositionEvaluation(fenced);
    expect(result).not.toBeNull();
    expect(result!.positions[0].signal_id).toBe("sig-plain");
  });

  it("returns null when positions field is missing", () => {
    const json = JSON.stringify({ actions: [] });
    const result = parsePositionEvaluation(json);
    expect(result).toBeNull();
  });

  it("returns null when top-level value is not an object", () => {
    const result = parsePositionEvaluation(JSON.stringify([1, 2, 3]));
    expect(result).toBeNull();
  });
});
