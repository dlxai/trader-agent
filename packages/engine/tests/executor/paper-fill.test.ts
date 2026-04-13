import { describe, it, expect } from "vitest";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import type { FillParams } from "../../src/executor/order-filler.js";

describe("paperFiller", () => {
  const filler = createPaperFiller({ slippagePct: 0.005 });

  it("fills buy at mid + slippage", async () => {
    const params: FillParams = { tokenId: "t1", midPrice: 0.50, sizeUsdc: 100, direction: "buy_yes", timestampMs: 1_000 };
    const fill = await filler.fillBuy(params);
    expect(fill.fillPrice).toBeCloseTo(0.50 * 1.005, 5);
    expect(fill.filledSize).toBe(100);
    expect(fill.filled).toBe(true);
    expect(fill.reason).toBe("filled");
  });

  it("fills sell at mid - slippage", async () => {
    const params: FillParams = { tokenId: "t1", midPrice: 0.60, sizeUsdc: 100, direction: "buy_yes", timestampMs: 1_000 };
    const fill = await filler.fillSell(params);
    expect(fill.fillPrice).toBeCloseTo(0.60 * 0.995, 5);
    expect(fill.filled).toBe(true);
  });
});
