/**
 * Polymarket CLOB API Client
 *
 * Provides real market metadata from Polymarket CLOB API
 * Docs: https://docs.polymarket.com/
 */

import { HttpsProxyAgent } from "https-proxy-agent";
import https from "node:https";
import type { MarketMetadata } from "./collector.js";

export interface PolymarketMarketData {
  marketId: string;
  marketTitle: string;
  resolvesAt: number;
  liquidity: number;
  description?: string;
  category?: string;
  outcomes?: Array<{ name: string; price: number }>;
}

interface ClobMarketResponse {
  condition_id: string;
  question: string;
  description: string;
  end_date_iso: string;
  market_slug: string;
  active: boolean;
  closed: boolean;
  tags?: string[];
  tokens: Array<{
    token_id: string;
    outcome: string;
    price: number;
  }>;
}

export interface PolymarketApiClient {
  getMarketData(marketId: string): Promise<PolymarketMarketData>;
}

export function createPolymarketApiClient(options?: {
  baseUrl?: string;
  proxyUrl?: string;
  maxRetries?: number;
  retryDelayMs?: number;
}): PolymarketApiClient {
  // Use CLOB API instead of Gamma API - it accepts conditionId
  const baseUrl = options?.baseUrl ?? "https://clob.polymarket.com";
  const proxyUrl = options?.proxyUrl;
  const maxRetries = options?.maxRetries ?? 3;
  const retryDelayMs = options?.retryDelayMs ?? 1000;

  async function fetchWithProxy(url: string): Promise<{ ok: boolean; status: number; statusText: string; json(): Promise<unknown> }> {
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

      if (proxyUrl) {
        console.log(`[polymarket-api] Using proxy: ${proxyUrl} for ${url}`);
        requestOptions.agent = new HttpsProxyAgent(proxyUrl);
      } else {
        console.log(`[polymarket-api] No proxy configured for ${url}`);
      }

      const req = https.request(requestOptions, (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          resolve({
            ok: res.statusCode! >= 200 && res.statusCode! < 300,
            status: res.statusCode!,
            statusText: res.statusMessage || "",
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

  async function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  return {
    async getMarketData(marketId: string): Promise<PolymarketMarketData> {
      let lastError: Error | undefined;

      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          // Use CLOB API - it accepts conditionId directly in the path
          const url = `${baseUrl}/markets/${encodeURIComponent(marketId)}`;
          const response = await fetchWithProxy(url);

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          const data = (await response.json()) as ClobMarketResponse;

          return {
            marketId: data.condition_id,
            marketTitle: data.question,
            resolvesAt: new Date(data.end_date_iso).getTime(),
            liquidity: 0, // CLOB API doesn't provide liquidity directly
            description: data.description,
            category: data.tags?.[0] ?? "",
            outcomes: data.tokens?.map(t => ({ name: t.outcome, price: t.price })) ?? [],
          };
        } catch (error) {
          lastError = error as Error;
          console.warn(`[polymarket-api] Attempt ${attempt}/${maxRetries} failed for ${marketId}: ${lastError.message}`);

          if (attempt < maxRetries) {
            await sleep(retryDelayMs * attempt); // Exponential backoff
          }
        }
      }

      console.error(`[polymarket-api] All ${maxRetries} attempts failed for ${marketId}`);
      throw lastError;
    },
  };
}

/**
 * Create a market metadata provider that uses real Polymarket API
 * Throws error if API fails (no fallback to placeholder)
 */
export function createPolymarketMarketMetadataProvider(options?: {
  proxyUrl?: string;
}): (marketId: string) => Promise<MarketMetadata> {
  const client = createPolymarketApiClient(options?.proxyUrl ? { proxyUrl: options.proxyUrl } : undefined);

  return async (marketId: string) => {
    const data = await client.getMarketData(marketId);
    console.log(`[polymarket-api] Fetched real data for ${marketId}: ${data.marketTitle}`);
    return {
      marketId: data.marketId,
      marketTitle: data.marketTitle,
      resolvesAt: data.resolvesAt,
      liquidity: data.liquidity,
    };
  };
}
