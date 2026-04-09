import { describe, it, expect } from "vitest";
import { createTriggerEvaluator } from "../../src/collector/trigger-evaluator.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { WindowStats } from "../../src/collector/rolling-window.js";

const baseMarket = {
  marketId: "m1",
  marketTitle: "Will it happen?",
  resolvesAt: Date.now() + 7_200_000,
  currentMidPrice: 0.55,
  liquidity: 6000,
};

const baseWindow1m: WindowStats = {
  volume: 3500,
  netFlow: 3200,
  uniqueTraders: 4,
  priceMove: 0.0,
};
const baseWindow5m: WindowStats = {
  volume: 10_000,
  netFlow: 8000,
  uniqueTraders: 12,
  priceMove: 0.04,
};

describe("triggerEvaluator", () => {
  const evalTrigger = createTriggerEvaluator(DEFAULT_CONFIG);
  // Default trade size that passes the minTradeUsdc threshold ($200)
  const defaultTradeSize = 500;

  it("accepts a clean signal that meets all thresholds", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: baseWindow1m,
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(true);
    if (result.accepted) {
      expect(result.direction).toBe("buy_yes");
    }
  });

  it("rejects when net flow is below threshold", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: { ...baseWindow1m, netFlow: 500 },
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("net_flow_below_threshold");
    }
  });

  it("rejects when unique traders are below threshold (no large-order exemption)", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: { ...baseWindow1m, uniqueTraders: 2 },
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("unique_traders_below_threshold");
    }
  });

  it("rejects when price inside static dead zone [0.60, 0.85]", () => {
    const result = evalTrigger({
      market: { ...baseMarket, currentMidPrice: 0.72 },
      window1m: baseWindow1m,
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("inside_dead_zone");
    }
  });

  it("rejects when time-to-resolve is too short", () => {
    const result = evalTrigger({
      market: { ...baseMarket, resolvesAt: Date.now() + 60_000 },
      window1m: baseWindow1m,
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("time_to_resolve_too_short");
    }
  });

  it("rejects when price move is too small", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: baseWindow1m,
      window5m: { ...baseWindow5m, priceMove: 0.01 },
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("price_move_below_threshold");
    }
  });

  it("rejects when market title matches blacklist", () => {
    const result = evalTrigger({
      market: { ...baseMarket, marketTitle: "Bitcoin Up or Down in next hour" },
      window1m: baseWindow1m,
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("blacklisted_market");
    }
  });

  it("applies large-single-trade exemption to bypass unique-traders requirement", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: { ...baseWindow1m, uniqueTraders: 1 },
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: 6000,
    });
    expect(result.accepted).toBe(true);
  });

  it("applies large-net-flow exemption to bypass unique-traders requirement", () => {
    const result = evalTrigger({
      market: baseMarket,
      window1m: { ...baseWindow1m, uniqueTraders: 1, netFlow: 12_000 },
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: defaultTradeSize,
    });
    expect(result.accepted).toBe(true);
  });

  it("does NOT exempt dead zone even with large order", () => {
    const result = evalTrigger({
      market: { ...baseMarket, currentMidPrice: 0.72 },
      window1m: baseWindow1m,
      window5m: baseWindow5m,
      nowMs: Date.now(),
      latestTradeSizeUsdc: 8000,
    });
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.rejection).toBe("inside_dead_zone");
    }
  });
});
