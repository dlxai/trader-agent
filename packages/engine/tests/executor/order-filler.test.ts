import { describe, it, expect } from "vitest";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import type { FillParams } from "../../src/executor/order-filler.js";

describe("PaperFiller as OrderFiller", () => {
  const filler = createPaperFiller({ slippagePct: 0.005 });

  it("fillBuy returns filled result with slippage", async () => {
    const params: FillParams = {
      tokenId: "tok1",
      midPrice: 0.50,
      sizeUsdc: 100,
      direction: "buy_yes",
      timestampMs: Date.now(),
    };
    const result = await filler.fillBuy(params);
    expect(result.filled).toBe(true);
    expect(result.fillPrice).toBeCloseTo(0.5025, 4);
    expect(result.filledSize).toBe(100);
    expect(result.reason).toBe("filled");
  });

  it("fillSell returns filled result with slippage", async () => {
    const params: FillParams = {
      tokenId: "tok1",
      midPrice: 0.60,
      sizeUsdc: 100,
      direction: "buy_yes",
      timestampMs: Date.now(),
    };
    const result = await filler.fillSell(params);
    expect(result.filled).toBe(true);
    expect(result.fillPrice).toBeCloseTo(0.597, 4);
    expect(result.filledSize).toBe(100);
    expect(result.reason).toBe("filled");
  });
});
