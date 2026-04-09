import type { TraderConfig } from "../config/schema.js";
import type { WindowStats } from "./rolling-window.js";
import type { Direction } from "../db/types.js";

export type RejectionReason =
  | "trade_size_below_threshold"
  | "net_flow_below_threshold"
  | "unique_traders_below_threshold"
  | "price_move_below_threshold"
  | "price_move_direction_mismatch"
  | "price_out_of_range"
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

    // 1. Trade size filter (单笔金额过滤)
    if (latestTradeSizeUsdc < cfg.minTradeUsdc) {
      return { accepted: false, rejection: "trade_size_below_threshold" };
    }

    // 2. Blacklist check (cheapest first)
    const titleLower = market.marketTitle.toLowerCase();
    for (const sub of cfg.marketBlacklistSubstrings) {
      if (titleLower.includes(sub.toLowerCase())) {
        return { accepted: false, rejection: "blacklisted_market" };
      }
    }

    // 3. Price range check (价格允许值域: 0.01 ≤ price ≤ 0.99)
    if (market.currentMidPrice < 0.01 || market.currentMidPrice > 0.99) {
      return { accepted: false, rejection: "price_out_of_range" };
    }

    // 4. Dead zone (静态死亡区间: [0.60, 0.85])
    const [dzMin, dzMax] = cfg.staticDeadZone;
    if (market.currentMidPrice >= dzMin && market.currentMidPrice <= dzMax) {
      return { accepted: false, rejection: "inside_dead_zone" };
    }

    // 5. Time to resolve (剩余时间检查)
    // 小于 30 分钟：剩余时间太短，忽略
    // 大于 6 小时：时间太长不确定性高，忽略
    // 注意：已过期市场（负数）允许通过，只要有交易活动
    const HOUR = 3600;
    const secToResolve = Math.floor((market.resolvesAt - nowMs) / 1000);
    if (secToResolve >= 0 && secToResolve < 30 * 60) {
      return { accepted: false, rejection: "time_to_resolve_too_short" };
    }
    if (secToResolve > 6 * HOUR) {
      return { accepted: false, rejection: "time_to_resolve_too_long" };
    }

    // 6. Liquidity (流动性 ≥ $5000)
    if (market.liquidity < cfg.minLiquidityUsdc) {
      return { accepted: false, rejection: "liquidity_below_threshold" };
    }

    // 7. Price move (赔率移动 ≥ 3%)
    if (Math.abs(window5m.priceMove) < cfg.minPriceMove5m) {
      return { accepted: false, rejection: "price_move_below_threshold" };
    }

    // 8. Price move direction must match net flow direction (赔率移动方向与净流入一致)
    const priceMoveDirection = window5m.priceMove >= 0 ? 1 : -1;
    const netFlowDirection = window1m.netFlow >= 0 ? 1 : -1;
    if (priceMoveDirection !== netFlowDirection) {
      return { accepted: false, rejection: "price_move_direction_mismatch" };
    }

    // 9. Net flow (净流入 ≥ $3000)
    if (Math.abs(window1m.netFlow) < cfg.minNetFlow1mUsdc) {
      return { accepted: false, rejection: "net_flow_below_threshold" };
    }

    // 10. Unique traders (独立trader数 ≥ 3)
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
