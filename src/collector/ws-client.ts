/**
 * Polymarket WebSocket client.
 *
 * Protocol reference: @polymarket/clob-client README + Polymarket docs at
 * https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
 *
 * We subscribe to the "market" channel and parse trade events into the
 * plugin's internal Trade type. Reconnect uses exponential backoff.
 */
import WebSocket from "ws";
import type { Trade } from "./rolling-window.js";

export interface WsClientOptions {
  url: string;
  onTrade: (trade: Trade & { marketId: string }) => void;
  onError: (err: Error) => void;
  reconnectInitialMs?: number;
  reconnectMaxMs?: number;
}

export interface PolymarketWsClient {
  connect(): Promise<void>;
  close(): void;
}

interface RawTradeEvent {
  event_type: string;
  market: string;
  asset_id?: string;
  price: string;
  side: string;
  size: string;
  taker?: string;
  timestamp: string;
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
      socket = new WebSocket(opts.url);
      socket.on("open", () => {
        backoffMs = opts.reconnectInitialMs ?? 1000;
        resolve();
      });
      socket.on("message", (data) => {
        try {
          const raw = JSON.parse(data.toString()) as RawTradeEvent;
          if (raw.event_type !== "trade") return;
          const side: "buy" | "sell" = raw.side.toLowerCase() === "buy" ? "buy" : "sell";
          opts.onTrade({
            marketId: raw.market,
            timestampMs: parseInt(raw.timestamp, 10),
            address: raw.taker ?? "unknown",
            sizeUsdc: parseFloat(raw.size),
            side,
            price: parseFloat(raw.price),
          });
        } catch (err) {
          opts.onError(err as Error);
        }
      });
      socket.on("error", (err) => {
        opts.onError(err as Error);
        reject(err);
      });
      socket.on("close", () => {
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
