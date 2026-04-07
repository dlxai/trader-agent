import { describe, it, expect } from "vitest";
import { createPaperFiller } from "../../src/executor/paper-fill.js";

describe("paperFiller", () => {
  const filler = createPaperFiller({ slippagePct: 0.005 });

  it("fills buy at mid + slippage", () => {
    const fill = filler.fillBuy({ midPrice: 0.50, sizeUsdc: 100, timestampMs: 1_000 });
    expect(fill.fillPrice).toBeCloseTo(0.50 * 1.005, 5);
    expect(fill.sizeUsdc).toBe(100);
    expect(fill.timestampMs).toBe(1_000);
  });

  it("fills sell at mid - slippage", () => {
    const fill = filler.fillSell({ midPrice: 0.60, sizeUsdc: 100, timestampMs: 1_000 });
    expect(fill.fillPrice).toBeCloseTo(0.60 * 0.995, 5);
  });
});
