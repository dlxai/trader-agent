import { describe, it, expect } from "vitest";
import { evaluateAutoApply } from "../src/auto-apply.js";

describe("auto-apply", () => {
  it("approves a high-confidence proposal", () => {
    const decision = evaluateAutoApply({
      sample_count: 35,
      expected_delta_winrate: 0.06,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(true);
  });

  it("rejects when sample_count too small", () => {
    const decision = evaluateAutoApply({
      sample_count: 20,
      expected_delta_winrate: 0.10,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("sample");
  });

  it("rejects when expected delta winrate too small", () => {
    const decision = evaluateAutoApply({
      sample_count: 50,
      expected_delta_winrate: 0.03,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("delta");
  });

  it("rejects locked field even with high confidence", () => {
    const decision = evaluateAutoApply({
      sample_count: 100,
      expected_delta_winrate: 0.20,
      field: "static_dead_zone_min",
      proposed_value: "0.55",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("locked");
  });

  it("rejects fields that affect max single trade loss", () => {
    const decision = evaluateAutoApply({
      sample_count: 100,
      expected_delta_winrate: 0.10,
      field: "max_single_trade_loss_usdc",
      proposed_value: "100",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("loss");
  });
});
