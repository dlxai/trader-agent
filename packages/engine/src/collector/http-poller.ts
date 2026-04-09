/**
 * HTTP Poller fallback for Polymarket data
 * Used when WebSocket connection fails
 */
import { HttpsProxyAgent } from "https-proxy-agent";
import https from "node:https";

export interface Trade {
  marketId: string;
  timestampMs: number;
  address: string;
  sizeUsdc: number;
  side: "buy" | "sell";
  price: number;
}

export interface HttpPollerOptions {
  onTrade: (trade: Trade) => void;
  onError: (err: Error) => void;
  proxyUrl?: string;
  pollIntervalMs?: number;
}

export interface HttpPoller {
  start(): void;
  stop(): void;
}

interface PolymarketTrade {
  transactionHash: string;
  timestamp: string;
  marketSlug: string;
  outcome: string;
  side: string;
  size: string;
  price: string;
  traderAddress: string;
  conditionId: string;
}

export function createHttpPoller(opts: HttpPollerOptions): HttpPoller {
  let intervalId: NodeJS.Timeout | null = null;
  let lastTimestamp = Date.now() - 60000; // Start from 1 minute ago

  const pollIntervalMs = opts.pollIntervalMs ?? 5000;

  async function fetchWithProxy(url: string): Promise<{ ok: boolean; json(): Promise<unknown> }> {
    return new Promise((resolve, reject) => {
      const parsedUrl = new URL(url);
      const requestOptions: https.RequestOptions = {
        hostname: parsedUrl.hostname,
        port: parsedUrl.port || 443,
        path: parsedUrl.pathname + parsedUrl.search,
        method: "GET",
        headers: {
          "Accept": "application/json",
          "User-Agent": "PolymarketTrader/1.0",
        },
      };

      if (opts.proxyUrl) {
        requestOptions.agent = new HttpsProxyAgent(opts.proxyUrl);
      }

      const req = https.request(requestOptions, (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          resolve({
            ok: res.statusCode! >= 200 && res.statusCode! < 300,
            json: async () => JSON.parse(data),
          });
        });
      });

      req.on("error", (err) => {
        reject(err);
      });

      req.setTimeout(30000, () => {
        req.destroy();
        reject(new Error("Request timeout"));
      });

      req.end();
    });
  }

  async function poll(): Promise<void> {
    try {
      // Use Polymarket's public API to get recent trades
      const url = `https://polymarket.com/api/trades?limit=100&since=${lastTimestamp}`;
      const response = await fetchWithProxy(url);

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.ok}`);
      }

      const trades = await response.json() as PolymarketTrade[];

      for (const trade of trades) {
        const timestampMs = new Date(trade.timestamp).getTime();
        if (timestampMs > lastTimestamp) {
          lastTimestamp = timestampMs;
        }

        opts.onTrade({
          marketId: trade.conditionId,
          timestampMs,
          address: trade.traderAddress,
          sizeUsdc: parseFloat(trade.size),
          side: trade.side.toLowerCase() as "buy" | "sell",
          price: parseFloat(trade.price),
        });
      }
    } catch (err) {
      opts.onError(err as Error);
    }
  }

  return {
    start(): void {
      console.log(`[http-poller] Starting HTTP polling (interval: ${pollIntervalMs}ms)`);
      poll(); // Initial poll
      intervalId = setInterval(poll, pollIntervalMs);
    },
    stop(): void {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    },
  };
}
