import type { TraderConfig } from "../config/schema.js";
import type { BucketStats } from "./statistics.js";

export interface KillDecision {
  kill: boolean;
  reason?: string;
}

export function decideKillSwitch(
  stats: Pick<BucketStats, "trade_count" | "win_count" | "win_rate" | "total_pnl_net_usdc">,
  cfg: TraderConfig
): KillDecision {
  if (stats.trade_count < cfg.killSwitchMinTrades) {
    return { kill: false };
  }
  if (stats.win_rate < cfg.killSwitchMaxWinRate) {
    return {
      kill: true,
      reason: `win rate ${(stats.win_rate * 100).toFixed(1)}% over ${stats.trade_count} trades < kill threshold ${(cfg.killSwitchMaxWinRate * 100).toFixed(1)}%`,
    };
  }
  return { kill: false };
}
