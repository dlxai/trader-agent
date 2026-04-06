import { describe, it, expect } from "vitest";
import { createMarketState } from "../../src/collector/market-state.js";

describe("marketState", () => {
  it("creates a fresh state for a new market", () => {
    const state = createMarketState({ idleGcMs: 600_000 });
    state.addTrade("m1", {
      timestampMs: 1_000,
      address: "a",
      sizeUsdc: 100,
      side: "buy",
      price: 0.55,
    });
    const snap = state.getSnapshot("m1", 1_000);
    expect(snap).not.toBeNull();
    expect(snap?.window1m.volume).toBe(100);
    expect(snap?.currentMidPrice).toBe(0.55);
  });

  it("returns null for unknown market", () => {
    const state = createMarketState({ idleGcMs: 600_000 });
    expect(state.getSnapshot("unknown", 1_000)).toBeNull();
  });

  it("GCs idle markets older than threshold", () => {
    const state = createMarketState({ idleGcMs: 100_000 });
    state.addTrade("m1", { timestampMs: 1_000, address: "a", sizeUsdc: 10, side: "buy", price: 0.5 });
    state.gc(200_000);
    expect(state.getSnapshot("m1", 200_000)).toBeNull();
  });

  it("isolates state across different markets", () => {
    const state = createMarketState({ idleGcMs: 600_000 });
    state.addTrade("m1", { timestampMs: 1_000, address: "a", sizeUsdc: 10, side: "buy", price: 0.5 });
    state.addTrade("m2", { timestampMs: 1_000, address: "a", sizeUsdc: 20, side: "buy", price: 0.7 });
    expect(state.getSnapshot("m1", 1_000)?.window1m.volume).toBe(10);
    expect(state.getSnapshot("m2", 1_000)?.window1m.volume).toBe(20);
  });
});
