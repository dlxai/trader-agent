import { describe, it, expect } from "vitest";
import { createRollingWindow } from "../../src/collector/rolling-window.js";

describe("rollingWindow", () => {
  it("tracks volume over a 60s window", () => {
    const w = createRollingWindow({ windowMs: 60_000 });
    w.add({ timestampMs: 1_000, address: "a", sizeUsdc: 100, side: "buy", price: 0.55 });
    w.add({ timestampMs: 30_000, address: "b", sizeUsdc: 200, side: "sell", price: 0.54 });
    const stats = w.stats(30_000);
    expect(stats.volume).toBe(300);
  });

  it("computes net flow (buy minus sell)", () => {
    const w = createRollingWindow({ windowMs: 60_000 });
    w.add({ timestampMs: 1_000, address: "a", sizeUsdc: 500, side: "buy", price: 0.55 });
    w.add({ timestampMs: 10_000, address: "b", sizeUsdc: 200, side: "sell", price: 0.54 });
    expect(w.stats(10_000).netFlow).toBe(300);
  });

  it("drops trades older than window", () => {
    const w = createRollingWindow({ windowMs: 60_000 });
    w.add({ timestampMs: 1_000, address: "a", sizeUsdc: 100, side: "buy", price: 0.55 });
    const stats = w.stats(100_000);
    expect(stats.volume).toBe(0);
  });

  it("counts unique traders", () => {
    const w = createRollingWindow({ windowMs: 60_000 });
    w.add({ timestampMs: 1_000, address: "a", sizeUsdc: 100, side: "buy", price: 0.55 });
    w.add({ timestampMs: 2_000, address: "b", sizeUsdc: 100, side: "buy", price: 0.55 });
    w.add({ timestampMs: 3_000, address: "a", sizeUsdc: 100, side: "buy", price: 0.55 });
    expect(w.stats(3_000).uniqueTraders).toBe(2);
  });

  it("computes price move (last minus first within window)", () => {
    const w = createRollingWindow({ windowMs: 300_000 });
    w.add({ timestampMs: 1_000, address: "a", sizeUsdc: 100, side: "buy", price: 0.50 });
    w.add({ timestampMs: 100_000, address: "b", sizeUsdc: 100, side: "buy", price: 0.52 });
    w.add({ timestampMs: 200_000, address: "c", sizeUsdc: 100, side: "buy", price: 0.55 });
    const stats = w.stats(200_000);
    expect(stats.priceMove).toBeCloseTo(0.05, 5);
  });
});
