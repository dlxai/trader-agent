import type { TraderConfig } from "./schema.js";

export const DEFAULT_CONFIG: TraderConfig = {
  minTradeUsdc: 200,
  minNetFlow1mUsdc: 3000,
  minUniqueTraders1m: 3,
  minPriceMove5m: 0.03,
  minLiquidityUsdc: 5000,
  minTimeToResolveSec: 1800,       // 30 minutes
  maxTimeToResolveSec: 21600,      // 6 hours
  staticDeadZone: [0.60, 0.85],
  botBurstCount: 10,
  botBurstWindowMs: 1000,
  largeSingleTradeUsdc: 5000,
  largeNetFlowUsdc: 10_000,
  kellyMultiplier: 0.25,
  minPositionUsdc: 50,
  maxPositionUsdc: 300,
  maxSingleTradeLossUsdc: 50,
  maxTotalPositionUsdc: 2000,
  maxOpenPositions: 8,
  gasPerTradeUsdc: 0.20,
  stopLossPctNormal: 0.07,
  stopLossPctLateStage: 0.03,
  lateStageThresholdSec: 1800,
  takeProfitPct: 0.10,
  maxHoldingSec: 14_400,
  expirySafetyBufferSec: 300,
  dailyLossHaltPct: 0.02,
  weeklyLossHaltPct: 0.04,
  killSwitchMinTrades: 10,
  killSwitchMaxWinRate: 0.45,
  totalDrawdownHaltPct: 0.10,
  paperSlippagePct: 0.005,
  // CLOB Market WebSocket for orderbook/price data (持仓价格订阅)
  // Endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/market
  polymarketClobWsUrl: "wss://ws-subscriptions-clob.polymarket.com/ws/market",
  // RTDS WebSocket for trade activity stream (交易活动流)
  // Endpoint: wss://ws-live-data.polymarket.com
  polymarketActivityWsUrl: "wss://ws-live-data.polymarket.com",
  marketBlacklistSubstrings: ["up or down"],
  llmTimeoutMs: 30_000,
  // Analyzer LLM model (default to Claude Opus for best reasoning)
  analyzerModel: "claude-opus-4",
};
