import { describe, it, expect } from "vitest";
import { packContext } from "../../src/analyzer/context-packer.js";
import type { TriggerEvent } from "../../src/bus/types.js";

const trigger: TriggerEvent = {
  type: "trigger",
  market_id: "m1",
  market_title: "Will it rain tomorrow?",
  resolves_at: Date.now() + 7_200_000,
  triggered_at: Date.now(),
  direction: "buy_yes",
  snapshot: {
    volume_1m: 3500,
    net_flow_1m: 3200,
    unique_traders_1m: 4,
    price_move_5m: 0.04,
    liquidity: 6000,
    current_mid_price: 0.55,
  },
};

describe("packContext", () => {
  it("includes all required fields in the prompt", () => {
    const prompt = packContext(trigger);
    expect(prompt).toContain("Will it rain tomorrow?");
    expect(prompt).toContain("Current price: 0.5500");
    expect(prompt).toContain("Net flow (1m)");
    expect(prompt).toContain("3200");
    expect(prompt).toContain("Unique traders (1m): 4");
    expect(prompt).toContain("JSON");
    expect(prompt).toContain("verdict");
  });

  it("includes time-to-resolve in human-readable form", () => {
    const prompt = packContext(trigger);
    expect(prompt).toMatch(/Resolves in: (1h \d+m|\dh \d+m|[5-9][0-9] minutes)/);
  });
});
