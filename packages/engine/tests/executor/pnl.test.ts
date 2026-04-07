import { describe, it, expect } from "vitest";
import { computePnL } from "../../src/executor/pnl.js";

describe("computePnL", () => {
  it("computes gross, fees, slippage, gas, and net for a winning buy_yes", () => {
    const result = computePnL({
      direction: "buy_yes",
      sizeUsdc: 100,
      entryPrice: 0.50,
      exitPrice: 0.60,
      feePct: 0.005,
      slippagePct: 0.005,
      gasUsdc: 0.20,
    });
    expect(result.pnlGross).toBeCloseTo(20, 2);
    expect(result.fees).toBeCloseTo(100 * 0.005 + 120 * 0.005, 2);
    expect(result.slippage).toBeCloseTo(100 * 0.005 + 120 * 0.005, 2);
    expect(result.gas).toBe(0.20);
    expect(result.pnlNet).toBeCloseTo(
      result.pnlGross - result.fees - result.slippage - result.gas,
      2
    );
  });

  it("computes correct loss for a losing buy_no", () => {
    const result = computePnL({
      direction: "buy_no",
      sizeUsdc: 100,
      entryPrice: 0.30,
      exitPrice: 0.20,
      feePct: 0,
      slippagePct: 0,
      gasUsdc: 0,
    });
    expect(result.pnlGross).toBeCloseTo(-33.33, 1);
  });

  it("includes gas fee in net PnL even for tiny trades", () => {
    const result = computePnL({
      direction: "buy_yes",
      sizeUsdc: 50,
      entryPrice: 0.50,
      exitPrice: 0.51,
      feePct: 0,
      slippagePct: 0,
      gasUsdc: 0.20,
    });
    expect(result.pnlNet).toBeCloseTo(0.80, 2);
  });
});
