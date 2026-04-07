import type { TraderConfig } from "../config/schema.js";
import type { EventBus } from "../bus/events.js";
import type { TriggerEvent } from "../bus/types.js";
import { createMarketState } from "./market-state.js";
import type { MarketState } from "./market-state.js";
import { createBotFilter } from "./bot-filter.js";
import type { BotFilter } from "./bot-filter.js";
import { createTriggerEvaluator } from "./trigger-evaluator.js";
import type { TriggerEvaluator } from "./trigger-evaluator.js";
import type { PolymarketWsClient } from "./ws-client.js";

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
  wsClientFactory: (onTrade: (t: RawTrade) => void) => PolymarketWsClient;
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
  let gcInterval: NodeJS.Timeout | null = null;

  async function getMeta(marketId: string): Promise<MarketMetadata> {
    let meta = marketMetaCache.get(marketId);
    if (!meta) {
      meta = await deps.marketMetadataProvider(marketId);
      marketMetaCache.set(marketId, meta);
    }
    return meta;
  }

  async function ingestTrade(trade: RawTrade): Promise<void> {
    if (trade.sizeUsdc < deps.config.minTradeUsdc) return;
    if (botFilter.isBot(trade.address, trade.timestampMs)) return;

    marketState.addTrade(trade.marketId, trade);
    const snapshot = marketState.getSnapshot(trade.marketId, trade.timestampMs);
    if (!snapshot) return;

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
    if (!result.accepted) return;

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

  return {
    async start(): Promise<void> {
      wsClient = deps.wsClientFactory((t) => {
        ingestTrade(t).catch((err) =>
          deps.logger.error(`[collector] ingestTrade error: ${String(err)}`)
        );
      });
      await wsClient.connect();
      gcInterval = setInterval(() => marketState.gc(Date.now()), 60_000);
      deps.logger.info("[collector] started");
    },
    stop(): void {
      wsClient?.close();
      if (gcInterval) clearInterval(gcInterval);
      deps.logger.info("[collector] stopped");
    },
    ingestTrade,
  };
}
