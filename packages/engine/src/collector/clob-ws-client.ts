/**
 * Polymarket CLOB Market WebSocket client for position price monitoring.
 *
 * Endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/market
 *
 * Used for:
 * - Subscribing to specific market orderbook updates
 * - Real-time price monitoring for open positions
 * - Stop-loss / take-profit evaluation
 *
 * Subscription format:
 *   {
 *     "assets_ids": ["asset_id_1", "asset_id_2", ...],
 *     "type": "market"
 *   }
 *
 * Events:
 *   - "book": Full orderbook snapshot
 *   - "price_change": Incremental price updates with best_bid/best_ask
 *   - "last_trade_price": Recent trade price
 */
import WebSocket from "ws";
import { HttpsProxyAgent } from "https-proxy-agent";

export interface ClobWsClientOptions {
  url: string;
  onPriceUpdate: (marketId: string, midPrice: number, timestampMs: number) => void;
  onError: (err: Error) => void;
  reconnectInitialMs?: number;
  reconnectMaxMs?: number;
  proxyUrl?: string;
}

export interface ClobWsClient {
  connect(): Promise<void>;
  close(): void;
  subscribeMarkets(assetIds: string[]): void;
}

interface PriceChangeEvent {
  event_type: "price_change";
  asset_id: string;
  best_bid?: string;
  best_ask?: string;
  price?: string;
  timestamp?: string;
}

interface BookEvent {
  event_type: "book";
  asset_id: string;
  bids: Array<{ price: string; size: string }>;
  asks: Array<{ price: string; size: string }>;
  timestamp?: string;
}

interface LastTradeEvent {
  event_type: "last_trade_price";
  asset_id: string;
  price: string;
  timestamp?: string;
}

type ClobEvent = PriceChangeEvent | BookEvent | LastTradeEvent;

export function createClobWsClient(opts: ClobWsClientOptions): ClobWsClient {
  let socket: WebSocket | null = null;
  let closed = false;
  let backoffMs = opts.reconnectInitialMs ?? 1000;
  const maxBackoff = opts.reconnectMaxMs ?? 30_000;
  let subscribedAssets: string[] = [];
  let pingInterval: NodeJS.Timeout | null = null;

  function scheduleReconnect(): void {
    if (closed) return;
    setTimeout(() => {
      if (closed) return;
      backoffMs = Math.min(backoffMs * 2, maxBackoff);
      connectInternal().catch((err) => opts.onError(err as Error));
    }, backoffMs);
  }

  function startPing(): void {
    if (pingInterval) clearInterval(pingInterval);
    pingInterval = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send("PING");
      }
    }, 10000);
  }

  function stopPing(): void {
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
  }

  function handleEvent(event: ClobEvent, timestampMs: number): void {
    let midPrice: number | undefined;
    let assetId: string | undefined;

    if (event.event_type === "price_change") {
      assetId = event.asset_id;
      if (event.best_bid && event.best_ask) {
        const bid = parseFloat(event.best_bid);
        const ask = parseFloat(event.best_ask);
        midPrice = (bid + ask) / 2;
      } else if (event.price) {
        midPrice = parseFloat(event.price);
      }
    } else if (event.event_type === "book") {
      assetId = event.asset_id;
      const bestBidEntry = event.bids?.[0];
      const bestAskEntry = event.asks?.[0];
      if (bestBidEntry && bestAskEntry) {
        const bestBid = parseFloat(bestBidEntry.price);
        const bestAsk = parseFloat(bestAskEntry.price);
        midPrice = (bestBid + bestAsk) / 2;
      }
    } else if (event.event_type === "last_trade_price") {
      assetId = event.asset_id;
      midPrice = parseFloat(event.price);
    }

    if (assetId && midPrice !== undefined) {
      opts.onPriceUpdate(assetId, midPrice, timestampMs);
    }
  }

  async function connectInternal(): Promise<void> {
    return new Promise((resolve, reject) => {
      const proxyUrl = opts.proxyUrl || process.env.https_proxy || process.env.HTTPS_PROXY;
      const wsOptions: WebSocket.ClientOptions = proxyUrl
        ? { agent: new HttpsProxyAgent(proxyUrl) }
        : {};

      socket = new WebSocket(opts.url, wsOptions);

      socket.on("open", () => {
        backoffMs = opts.reconnectInitialMs ?? 1000;
        startPing();

        // Resubscribe to previously subscribed markets
        if (subscribedAssets.length > 0) {
          subscribeMarketsInternal(subscribedAssets);
        }

        resolve();
      });

      socket.on("message", (data) => {
        try {
          const text = data.toString();
          if (text === "PONG") return;

          const event = JSON.parse(text) as ClobEvent;
          const timestampMs = Date.now();
          handleEvent(event, timestampMs);
        } catch (err) {
          // Ignore non-JSON messages
        }
      });

      socket.on("error", (err) => {
        console.error(`[clob-ws-client] WebSocket error: ${err.message}`);
        opts.onError(err as Error);
        reject(err);
      });

      socket.on("close", (code, reason) => {
        console.warn(`[clob-ws-client] WebSocket closed: code=${code}, reason=${reason}`);
        stopPing();
        scheduleReconnect();
      });
    });
  }

  function subscribeMarketsInternal(assetIds: string[]): void {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    const subscribeMsg = {
      assets_ids: assetIds,
      type: "market"
    };
    socket.send(JSON.stringify(subscribeMsg));
  }

  return {
    connect: connectInternal,
    close(): void {
      closed = true;
      stopPing();
      socket?.close();
    },
    subscribeMarkets(assetIds: string[]): void {
      subscribedAssets = [...new Set([...subscribedAssets, ...assetIds])];
      subscribeMarketsInternal(assetIds);
    }
  };
}
