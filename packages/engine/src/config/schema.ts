export interface TraderConfig {
  // Trigger thresholds (§4.2)
  minTradeUsdc: number;             // 200
  minNetFlow1mUsdc: number;         // 3000
  minUniqueTraders1m: number;       // 3
  minPriceMove5m: number;           // 0.03
  minLiquidityUsdc: number;         // 5000
  minTimeToResolveSec: number;      // 1800
  maxTimeToResolveSec: number;      // 259200
  // Dead zone (§4.3)
  staticDeadZone: [number, number]; // [0.60, 0.85]
  // Bot detection (§4.2)
  botBurstCount: number;            // 10
  botBurstWindowMs: number;         // 1000
  // Large order exemption (§4.2)
  largeSingleTradeUsdc: number;     // 5000
  largeNetFlowUsdc: number;         // 10000
  // Kelly (§6.1)
  kellyMultiplier: number;          // 0.25
  minPositionUsdc: number;          // 50
  maxPositionUsdc: number;          // 300
  maxSingleTradeLossUsdc: number;   // 50
  // Portfolio limits (§6.2)
  maxTotalPositionUsdc: number;     // 2000
  maxOpenPositions: number;         // 8
  gasPerTradeUsdc: number;          // 0.20
  // Exit rules (§5)
  stopLossPctNormal: number;        // 0.07
  stopLossPctLateStage: number;     // 0.03
  lateStageThresholdSec: number;    // 1800
  takeProfitPct: number;            // 0.10
  maxHoldingSec: number;            // 14400
  expirySafetyBufferSec: number;    // 300  (TBD from Polymarket CLOB docs)
  // Circuit breakers (§6.3)
  dailyLossHaltPct: number;         // 0.02
  weeklyLossHaltPct: number;        // 0.04
  killSwitchMinTrades: number;      // 10
  killSwitchMaxWinRate: number;     // 0.45
  totalDrawdownHaltPct: number;     // 0.10
  // Paper trading (§9)
  paperSlippagePct: number;         // 0.005
  // Polymarket (§3)
  polymarketWsUrl: string;          // wss://ws-subscriptions-clob.polymarket.com/ws/
  marketBlacklistSubstrings: string[]; // ["up or down"]
  // LLM (§7.1 Analyzer)
  llmTimeoutMs: number;             // 30000
}
