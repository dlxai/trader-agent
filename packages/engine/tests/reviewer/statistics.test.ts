import { describe, it, expect } from "vitest";
import { computeBucketStats } from "../../src/reviewer/statistics.js";
import type { SignalLogRow } from "../../src/db/types.js";

function closedTrade(bucket: number, netPnl: number): SignalLogRow {
  return {
    signal_id: `t-${bucket}-${netPnl}`,
    market_id: "m",
    market_title: "x",
    resolves_at: 0,
    triggered_at: 0,
    direction: "buy_yes",
    entry_price: bucket + 0.01,
    price_bucket: bucket,
    size_usdc: 100,
    kelly_fraction: 0.1,
    snapshot_volume_1m: 0,
    snapshot_net_flow_1m: 0,
    snapshot_unique_traders_1m: 0,
    snapshot_price_move_5m: 0,
    snapshot_liquidity: 0,
    llm_verdict: "real_signal",
    llm_confidence: 0.5,
    llm_reasoning: "",
    exit_at: 1,
    exit_price: 0,
    exit_reason: netPnl > 0 ? "A_TP" : "A_SL",
    pnl_gross_usdc: netPnl,
    fees_usdc: 0,
    slippage_usdc: 0,
    gas_usdc: 0.2,
    pnl_net_usdc: netPnl,
    holding_duration_sec: 1,
  };
}

describe("computeBucketStats", () => {
  it("returns empty stats for no trades", () => {
    expect(computeBucketStats([], { windowMs: 86_400_000, nowMs: 1000 })).toEqual([]);
  });

  it("computes per-bucket win rate", () => {
    const trades = [
      closedTrade(0.5, 10),
      closedTrade(0.5, 10),
      closedTrade(0.5, -5),
      closedTrade(0.5, -5),
    ];
    const stats = computeBucketStats(trades, { windowMs: 86_400_000, nowMs: 1000 });
    const b50 = stats.find((s) => s.price_bucket === 0.5);
    expect(b50?.trade_count).toBe(4);
    expect(b50?.win_count).toBe(2);
    expect(b50?.win_rate).toBe(0.5);
    expect(b50?.total_pnl_net_usdc).toBe(10);
  });

  it("separates different buckets", () => {
    const trades = [
      closedTrade(0.30, 5),
      closedTrade(0.30, 5),
      closedTrade(0.70, -10),
      closedTrade(0.70, -10),
    ];
    const stats = computeBucketStats(trades, { windowMs: 86_400_000, nowMs: 1000 });
    expect(stats.find((s) => s.price_bucket === 0.30)?.win_rate).toBe(1);
    expect(stats.find((s) => s.price_bucket === 0.70)?.win_rate).toBe(0);
  });
});
