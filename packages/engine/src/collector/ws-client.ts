/**
 * Polymarket WebSocket client.
 *
 * Uses the Real-Time Data WebSocket (RTDS) endpoint:
 *   wss://ws-live-data.polymarket.com
 *
 * Protocol reference: https://github.com/Polymarket/real-time-data-client
 *
 * Subscription message format for trades/activity:
 *   {
 *     "action": "subscribe",
 *     "subscriptions": [
 *       {
 *         "topic": "activity",
 *         "type": "trades",
 *         "filters": ""
 *       }
 *     ]
 *   }
 *
 * Trade event format:
 *   {
 *     "connection_id": "...",
 *     "timestamp": 1775653658045,
 *     "topic": "activity",
 *     "type": "trades",
 *     "payload": {
 *       "asset": "...",
 *       "conditionId": "0x...",
 *       "eventSlug": "...",
 *       "slug": "...",
 *       "outcome": "Yes" | "No",
 *       "outcomeIndex": 0 | 1,
 *       "price": 0.55,
 *       "side": "BUY" | "SELL",
 *       "size": 1000,
 *       "timestamp": 1775653658,
 *       "transactionHash": "0x...",
 *       "proxyWallet": "0x...",
 *       "name": "0x...",
 *       "pseudonym": "..."
 *     }
 *   }
 */
import WebSocket from "ws";
import { HttpsProxyAgent } from "https-proxy-agent";
import type { Trade } from "./rolling-window.js";

export interface WsClientOptions {
  url: string;
  onTrade: (trade: Trade & { marketId: string }) => void;
  onError: (err: Error) => void;
  reconnectInitialMs?: number;
  reconnectMaxMs?: number;
  proxyUrl?: string;
}

export interface PolymarketWsClient {
  connect(): Promise<void>;
  close(): void;
}

interface RawTradePayload {
  asset: string;
  conditionId: string;
  eventSlug: string;
  slug: string;
  outcome: string;
  outcomeIndex: number;
  price: number;
  side: string;
  size: number;
  timestamp: number;
  transactionHash: string;
  proxyWallet: string;
  name: string;
  pseudonym: string;
}

interface RawTradeEvent {
  connection_id: string;
  timestamp: number;
  topic: string;
  type: string;
  payload: RawTradePayload;
}

export function createPolymarketWsClient(opts: WsClientOptions): PolymarketWsClient {
  let socket: WebSocket | null = null;
  let closed = false;
  let backoffMs = opts.reconnectInitialMs ?? 1000;
  const maxBackoff = opts.reconnectMaxMs ?? 30_000;

  function scheduleReconnect(): void {
    if (closed) return;
    setTimeout(() => {
      if (closed) return;
      backoffMs = Math.min(backoffMs * 2, maxBackoff);
      connectInternal().catch((err) => opts.onError(err as Error));
    }, backoffMs);
  }

  async function connectInternal(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Support proxy for WebSocket connection
      const proxyUrl = opts.proxyUrl || process.env.https_proxy || process.env.HTTPS_PROXY;
      console.log(`[ws-client] Connecting to ${opts.url} ${proxyUrl ? 'via proxy ' + proxyUrl : 'directly'}`);
      const wsOptions: WebSocket.ClientOptions = proxyUrl
        ? { agent: new HttpsProxyAgent(proxyUrl) }
        : {};
      socket = new WebSocket(opts.url, wsOptions);
      console.log(`[ws-client] WebSocket instance created`);
      socket.on("open", () => {
        console.log(`[ws-client] WebSocket connected to ${opts.url}`);
        backoffMs = opts.reconnectInitialMs ?? 1000;
        // Subscribe to activity/trades channel
        const subscribeMsg = {
          action: "subscribe",
          subscriptions: [
            {
              topic: "activity",
              type: "trades",
              filters: ""
            }
          ]
        };
        socket?.send(JSON.stringify(subscribeMsg));
        console.log(`[ws-client] Subscribed to activity/trades`);
        resolve();
      });
      socket.on("message", (data) => {
        try {
          const raw = JSON.parse(data.toString()) as RawTradeEvent;
          // Only process activity/trades events
          if (raw.topic !== "activity" || raw.type !== "trades") {
            return;
          }

          const payload = raw.payload;
          const side: "buy" | "sell" = payload.side.toUpperCase() === "BUY" ? "buy" : "sell";

          // Use conditionId as marketId (CLOB API accepts conditionId)
          opts.onTrade({
            marketId: payload.conditionId,
            timestampMs: raw.timestamp,
            address: payload.proxyWallet || payload.name,
            sizeUsdc: payload.size,
            side,
            price: payload.price,
          });
        } catch (err) {
          // Ignore non-JSON or non-trade messages
        }
      });
      socket.on("error", (err) => {
        console.error(`[ws-client] WebSocket error: ${err.message}`);
        opts.onError(err as Error);
        reject(err);
      });
      socket.on("close", (code, reason) => {
        console.warn(`[ws-client] WebSocket closed: code=${code}, reason=${reason}`);
        scheduleReconnect();
      });
    });
  }

  return {
    connect: connectInternal,
    close(): void {
      closed = true;
      socket?.close();
    },
  };
}
