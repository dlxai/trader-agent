import type { TraderConfig } from "../config/schema.js";
import type { WindowStats } from "./rolling-window.js";
import type { Direction } from "../db/types.js";

export type RejectionReason =
  | "net_flow_below_threshold"
  | "unique_traders_below_threshold"
  | "price_move_below_threshold"
  | "liquidity_below_threshold"
  | "time_to_resolve_too_short"
  | "time_to_resolve_too_long"
  | "inside_dead_zone"
  | "blacklisted_market";

export interface TriggerInput {
  market: {
    marketId: string;
    marketTitle: string;
    resolvesAt: number;
    currentMidPrice: number;
    liquidity: number;
  };
  window1m: WindowStats;
  window5m: WindowStats;
  nowMs: number;
  latestTradeSizeUsdc?: number;
}

export interface TriggerAccepted {
  accepted: true;
  direction: Direction;
}
export interface TriggerRejected {
  accepted: false;
  rejection: RejectionReason;
}
export type TriggerResult = TriggerAccepted | TriggerRejected;

export type TriggerEvaluator = (input: TriggerInput) => TriggerResult;

export function createTriggerEvaluator(cfg: TraderConfig): TriggerEvaluator {
  return function evaluate(input: TriggerInput): TriggerResult {
    const { market, window1m, window5m, nowMs, latestTradeSizeUsdc = 0 } = input;

    // Blacklist check (cheapest first)
    const titleLower = market.marketTitle.toLowerCase();
    for (const sub of cfg.marketBlacklistSubstrings) {
      if (titleLower.includes(sub.toLowerCase())) {
        return { accepted: false, rejection: "blacklisted_market" };
      }
    }

    // Dead zone (even large orders do not get exemption — spec §4.2)
    const [dzMin, dzMax] = cfg.staticDeadZone;
    if (market.currentMidPrice >= dzMin && market.currentMidPrice <= dzMax) {
      return { accepted: false, rejection: "inside_dead_zone" };
    }

    // Time to resolve
    const secToResolve = Math.floor((market.resolvesAt - nowMs) / 1000);
    if (secToResolve < cfg.minTimeToResolveSec) {
      return { accepted: false, rejection: "time_to_resolve_too_short" };
    }
    if (secToResolve > cfg.maxTimeToResolveSec) {
      return { accepted: false, rejection: "time_to_resolve_too_long" };
    }

    // Liquidity
    if (market.liquidity < cfg.minLiquidityUsdc) {
      return { accepted: false, rejection: "liquidity_below_threshold" };
    }

    // Price move (from 5m window)
    if (Math.abs(window5m.priceMove) < cfg.minPriceMove5m) {
      return { accepted: false, rejection: "price_move_below_threshold" };
    }

    // Net flow (from 1m window)
    if (Math.abs(window1m.netFlow) < cfg.minNetFlow1mUsdc) {
      return { accepted: false, rejection: "net_flow_below_threshold" };
    }

    // Large order exemption: bypass unique traders requirement only
    const hasLargeExemption =
      latestTradeSizeUsdc >= cfg.largeSingleTradeUsdc ||
      Math.abs(window1m.netFlow) >= cfg.largeNetFlowUsdc;

    if (!hasLargeExemption && window1m.uniqueTraders < cfg.minUniqueTraders1m) {
      return { accepted: false, rejection: "unique_traders_below_threshold" };
    }

    // Direction from net flow sign
    const direction: Direction = window1m.netFlow >= 0 ? "buy_yes" : "buy_no";
    return { accepted: true, direction };
  };
}
