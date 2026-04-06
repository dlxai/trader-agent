import { describe, it, expect } from "vitest";
import { calculateKellyPosition } from "../../src/executor/kelly.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";

describe("calculateKellyPosition", () => {
  const cfg = DEFAULT_CONFIG;
  const capital = 10_000;

  it("returns 0 when Kelly fraction is negative (bad edge)", () => {
    const result = calculateKellyPosition({
      entryPrice: 0.55,
      winRate: 0.50,
      capital,
      config: cfg,
    });
    expect(result.size).toBe(0);
    expect(result.reason).toBe("kelly_non_positive");
  });

  it("returns 0 when Kelly fraction is 0 (break even)", () => {
    const result = calculateKellyPosition({
      entryPrice: 0.60,
      winRate: 0.60,
      capital,
      config: cfg,
    });
    expect(result.size).toBe(0);
    expect(result.reason).toBe("kelly_non_positive");
  });

  it("returns positive size at favorable edge", () => {
    const result = calculateKellyPosition({
      entryPrice: 0.50,
      winRate: 0.60,
      capital,
      config: cfg,
    });
    expect(result.size).toBeLessThanOrEqual(cfg.maxPositionUsdc);
    expect(result.size).toBeGreaterThan(0);
  });

  it("clamps size so single-trade loss cannot exceed maxSingleTradeLossUsdc", () => {
    const result = calculateKellyPosition({
      entryPrice: 0.95,
      winRate: 0.98,
      capital,
      config: cfg,
    });
    if (result.size > 0) {
      const maxLoss = result.size * 0.95;
      expect(maxLoss).toBeLessThanOrEqual(cfg.maxSingleTradeLossUsdc + 0.01);
    }
  });

  it("returns 0 when computed size is below minPositionUsdc", () => {
    const result = calculateKellyPosition({
      entryPrice: 0.50,
      winRate: 0.505,
      capital: 10_000,
      config: cfg,
    });
    expect(result.size).toBe(0);
    expect(result.reason).toBe("below_min_position");
  });

  it("applies kellyMultiplier (1/4 Kelly)", () => {
    const low = calculateKellyPosition({
      entryPrice: 0.50,
      winRate: 0.60,
      capital: 100_000,
      config: { ...cfg, kellyMultiplier: 0.25 },
    });
    const high = calculateKellyPosition({
      entryPrice: 0.50,
      winRate: 0.60,
      capital: 100_000,
      config: { ...cfg, kellyMultiplier: 0.50 },
    });
    expect(high.size).toBeGreaterThanOrEqual(low.size);
  });
});
