import type { TraderConfig } from "../config/schema.js";
import type { EventBus } from "../bus/events.js";
import type { TriggerEvent } from "../bus/types.js";
import type { Executor } from "../executor/executor.js";
import { createMarketState } from "./market-state.js";
import type { MarketState } from "./market-state.js";
import { createBotFilter } from "./bot-filter.js";
import type { BotFilter } from "./bot-filter.js";
import { createTriggerEvaluator } from "./trigger-evaluator.js";
import type { TriggerEvaluator } from "./trigger-evaluator.js";
import type { PolymarketWsClient } from "./ws-client.js";
import type { ClobWsClient } from "./clob-ws-client.js";
import { createHttpPoller, type HttpPoller } from "./http-poller.js";

export interface MarketMetadata {
  marketId: string;
  marketTitle: string;
  resolvesAt: number;
  liquidity: number;
}

interface RawTrade {
  marketId: string;
  timestampMs: number;
  address: string;
  sizeUsdc: number;
  side: "buy" | "sell";
  price: number;
}

export interface CollectorDeps {
  config: TraderConfig;
  bus: EventBus;
  executor: Executor;
  wsClientFactory: (onTrade: (t: RawTrade) => void) => PolymarketWsClient;
  clobWsClientFactory?: (onPriceUpdate: (marketId: string, midPrice: number, timestampMs: number) => void) => ClobWsClient;
  marketMetadataProvider: (marketId: string) => Promise<MarketMetadata>;
  logger: { info: (m: string) => void; warn: (m: string) => void; error: (m: string) => void };
}

export interface Collector {
  start(): Promise<void>;
  stop(): void;
  /** Test hook: feed a trade directly without WS. */
  ingestTrade(trade: RawTrade): Promise<void>;
}

export function createCollector(deps: CollectorDeps): Collector {
  const marketState: MarketState = createMarketState({ idleGcMs: 3_600_000 });
  const botFilter: BotFilter = createBotFilter({
    burstCount: deps.config.botBurstCount,
    windowMs: deps.config.botBurstWindowMs,
  });
  const evalTrigger: TriggerEvaluator = createTriggerEvaluator(deps.config);
  const marketMetaCache = new Map<string, MarketMetadata>();

  let wsClient: PolymarketWsClient | null = null;
  let httpPoller: HttpPoller | null = null;
  let clobWsClient: ClobWsClient | null = null;
  let gcInterval: NodeJS.Timeout | null = null;
  let positionMonitorInterval: NodeJS.Timeout | null = null;
  let useHttpFallback = false;

  async function getMeta(marketId: string): Promise<MarketMetadata> {
    let meta = marketMetaCache.get(marketId);
    if (!meta) {
      meta = await deps.marketMetadataProvider(marketId);
      marketMetaCache.set(marketId, meta);
    }
    return meta;
  }

  // Client-side filters for RTDS trade stream
  const SKIP_PATTERNS = [
    /test/i,           // Skip test markets
    /demo/i,           // Skip demo markets
    /fake/i,           // Skip fake markets
  ];

  async function ingestTrade(trade: RawTrade): Promise<void> {
    // Filter 1: Minimum trade size (configurable, default $200)
    if (trade.sizeUsdc < deps.config.minTradeUsdc) {
      return;
    }

    // Filter 2: Skip tiny trades (noise reduction, hardcoded at $10)
    if (trade.sizeUsdc < 10) {
      return;
    }

    // Filter 3: Bot detection
    if (botFilter.isBot(trade.address, trade.timestampMs)) {
      console.log(`[collector] Trade rejected: bot detected`);
      return;
    }

    // Filter 4: Skip invalid prices
    if (trade.price <= 0 || trade.price >= 1) {
      return;
    }

    marketState.addTrade(trade.marketId, trade);
    const snapshot = marketState.getSnapshot(trade.marketId, trade.timestampMs);
    if (!snapshot) return;

    // Notify executor of price update for position monitoring (stop-loss / take-profit)
    deps.executor.onPriceTick(trade.marketId, snapshot.currentMidPrice, trade.timestampMs);

    console.log(`[collector] Evaluating trigger for ${trade.marketId}: netFlow=$${snapshot.window1m.netFlow}, traders=${snapshot.window1m.uniqueTraders}, priceMove=${snapshot.window5m.priceMove}`);

    const meta = await getMeta(trade.marketId);
    const result = evalTrigger({
      market: {
        marketId: meta.marketId,
        marketTitle: meta.marketTitle,
        resolvesAt: meta.resolvesAt,
        currentMidPrice: snapshot.currentMidPrice,
        liquidity: meta.liquidity,
      },
      window1m: snapshot.window1m,
      window5m: snapshot.window5m,
      nowMs: trade.timestampMs,
      latestTradeSizeUsdc: trade.sizeUsdc,
    });
    if (!result.accepted) {
      console.log(`[collector] Trigger rejected: ${result.rejection}`);
      return;
    }
    console.log(`[collector] Trigger accepted: ${result.direction}`);

    const event: TriggerEvent = {
      type: "trigger",
      market_id: meta.marketId,
      market_title: meta.marketTitle,
      resolves_at: meta.resolvesAt,
      triggered_at: trade.timestampMs,
      direction: result.direction,
      snapshot: {
        volume_1m: snapshot.window1m.volume,
        net_flow_1m: snapshot.window1m.netFlow,
        unique_traders_1m: snapshot.window1m.uniqueTraders,
        price_move_5m: snapshot.window5m.priceMove,
        liquidity: meta.liquidity,
        current_mid_price: snapshot.currentMidPrice,
      },
    };
    deps.bus.publishTrigger(event);
    deps.logger.info(`[collector] trigger published for ${meta.marketId} (${result.direction})`);
  }

  // Update CLOB WebSocket subscriptions based on open positions
  function updateClobSubscriptions(): void {
    if (!clobWsClient) return;
    const openPositions = deps.executor.openPositions();
    if (openPositions.length === 0) return;
    
    // Subscribe to all markets with open positions
    const marketIds = openPositions.map(p => p.market_id);
    clobWsClient.subscribeMarkets(marketIds);
  }

  return {
    async start(): Promise<void> {
      console.log(`[collector] Starting collector...`);
      
      // Try WebSocket first, fallback to HTTP polling if it fails
      try {
        wsClient = deps.wsClientFactory((t) => {
          ingestTrade(t).catch((err) =>
            deps.logger.error(`[collector] ingestTrade error: ${String(err)}`)
          );
        });
        console.log(`[collector] Connecting WebSocket client...`);
        await wsClient.connect();
        console.log(`[collector] WebSocket connected successfully`);
      } catch (wsErr) {
        console.warn(`[collector] WebSocket failed, using HTTP fallback: ${String(wsErr)}`);
        useHttpFallback = true;
        httpPoller = createHttpPoller({
          onTrade: (t) => {
            ingestTrade(t).catch((err) =>
              deps.logger.error(`[collector] ingestTrade error: ${String(err)}`)
            );
          },
          onError: (err) => {
            deps.logger.error(`[http-poller] error: ${err.message}`);
          },
          proxyUrl: deps.config.proxyUrl,
          pollIntervalMs: 5000,
        });
        httpPoller.start();
      }
      
      // Start CLOB WebSocket for position price monitoring if factory provided
      if (deps.clobWsClientFactory && !useHttpFallback) {
        clobWsClient = deps.clobWsClientFactory((marketId, midPrice, timestampMs) => {
          // Notify executor of price update for stop-loss/take-profit
          deps.executor.onPriceTick(marketId, midPrice, timestampMs);
        });
        await clobWsClient.connect();
        
        // Periodically update CLOB subscriptions based on open positions
        positionMonitorInterval = setInterval(() => {
          updateClobSubscriptions();
        }, 30_000); // Check every 30 seconds
      }
      
      gcInterval = setInterval(() => marketState.gc(Date.now()), 60_000);
      deps.logger.info(`[collector] started (mode: ${useHttpFallback ? 'HTTP polling' : 'WebSocket'})`);
    },
    stop(): void {
      wsClient?.close();
      httpPoller?.stop();
      clobWsClient?.close();
      if (gcInterval) clearInterval(gcInterval);
      if (positionMonitorInterval) clearInterval(positionMonitorInterval);
      deps.logger.info("[collector] stopped");
    },
    ingestTrade,
  };
}
