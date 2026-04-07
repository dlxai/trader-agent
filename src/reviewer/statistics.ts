import type { SignalLogRow } from "../db/types.js";

export interface BucketStats {
  price_bucket: number;
  trade_count: number;
  win_count: number;
  win_rate: number;
  total_pnl_net_usdc: number;
}

export function computeBucketStats(
  trades: SignalLogRow[],
  opts: { windowMs: number; nowMs: number }
): BucketStats[] {
  const cutoff = opts.nowMs - opts.windowMs;
  const filtered = trades.filter((t) => t.exit_at !== null && t.exit_at >= cutoff);
  const byBucket = new Map<number, { count: number; wins: number; pnl: number }>();
  for (const t of filtered) {
    if (t.pnl_net_usdc === null) continue;
    const entry = byBucket.get(t.price_bucket) ?? { count: 0, wins: 0, pnl: 0 };
    entry.count++;
    if (t.pnl_net_usdc > 0) entry.wins++;
    entry.pnl += t.pnl_net_usdc;
    byBucket.set(t.price_bucket, entry);
  }
  const out: BucketStats[] = [];
  for (const [bucket, agg] of byBucket.entries()) {
    out.push({
      price_bucket: bucket,
      trade_count: agg.count,
      win_count: agg.wins,
      win_rate: agg.count > 0 ? agg.wins / agg.count : 0,
      total_pnl_net_usdc: agg.pnl,
    });
  }
  return out.sort((a, b) => a.price_bucket - b.price_bucket);
}
