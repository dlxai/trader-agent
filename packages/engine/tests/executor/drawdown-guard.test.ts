import { describe, it, expect } from "vitest";
import { createDrawdownGuard } from "../../src/executor/drawdown-guard.js";
import type { DrawdownGuardConfig } from "../../src/config/schema.js";

const defaultConfig: DrawdownGuardConfig = {
  enabled: true,
  minProfitPct: 0.05,
  maxDrawdownFromPeak: 0.40,
};

describe("createDrawdownGuard", () => {
  it("does not trigger when profit is below minProfitPct", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", 0.10); // peak = 10%
    // current profit 3% < minProfitPct 5%
    expect(guard.shouldExit("s1", 0.03)).toBe(false);
  });

  it("does not trigger when drawdown is below threshold", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", 0.10); // peak = 10%
    // current = 8%, drawdown = (10-8)/10 = 20% < 40%
    expect(guard.shouldExit("s1", 0.08)).toBe(false);
  });

  it("triggers when profit above minProfitPct AND drawdown exceeds threshold", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", 0.10); // peak = 10%
    // current = 5.5%, drawdown = (10 - 5.5) / 10 = 45% >= 40%
    expect(guard.shouldExit("s1", 0.055)).toBe(true);
  });

  it("does nothing when disabled", () => {
    const guard = createDrawdownGuard({ ...defaultConfig, enabled: false });
    guard.onPriceTick("s1", 0.20); // should be ignored
    expect(guard.shouldExit("s1", 0.05)).toBe(false);
  });

  it("clears state after position close, resets peak", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", 0.10); // peak = 10%
    guard.clear("s1");
    // After clear, no peak exists, shouldExit should return false
    expect(guard.shouldExit("s1", 0.055)).toBe(false);
    // Re-establish a new peak and verify it works again
    guard.onPriceTick("s1", 0.10);
    expect(guard.shouldExit("s1", 0.055)).toBe(true);
  });

  it("does not trigger when no peak has been recorded", () => {
    const guard = createDrawdownGuard(defaultConfig);
    expect(guard.shouldExit("unknown", 0.055)).toBe(false);
  });

  it("does not trigger when peak is zero or negative (no meaningful profit peak)", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", -0.05); // negative peak
    expect(guard.shouldExit("s1", -0.10)).toBe(false);
  });

  it("tracks peak correctly across multiple ticks", () => {
    const guard = createDrawdownGuard(defaultConfig);
    guard.onPriceTick("s1", 0.06);
    guard.onPriceTick("s1", 0.12); // new peak
    guard.onPriceTick("s1", 0.08); // drop, peak stays at 12%
    // drawdown = (12 - 8) / 12 = 33% < 40%, should not exit
    expect(guard.shouldExit("s1", 0.08)).toBe(false);
    // drop further: (12 - 6) / 12 = 50% >= 40%, should exit
    expect(guard.shouldExit("s1", 0.06)).toBe(true);
  });
});
