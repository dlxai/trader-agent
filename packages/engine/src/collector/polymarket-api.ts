/**
 * Polymarket CLOB API Client
 * 
 * Provides real market metadata from Polymarket Gamma API
 * Docs: https://docs.polymarket.com/
 */

import { HttpsProxyAgent } from "https-proxy-agent";

export interface PolymarketMarketData {
  marketId: string;
  marketTitle: string;
  resolvesAt: number;
  liquidity: number;
  description?: string;
  category?: string;
  outcomes?: Array<{ name: string; price: number }>;
}

interface GammaMarketResponse {
  id: string;
  question: string;
  description: string;
  category: string;
  resolution_date: string;
  liquidity: string;
  outcomes: Array<{
    name: string;
    price: number;
  }>;
}

export interface PolymarketApiClient {
  getMarketData(marketId: string): Promise<PolymarketMarketData>;
}

export function createPolymarketApiClient(options?: {
  baseUrl?: string;
  proxyUrl?: string;
}): PolymarketApiClient {
  const baseUrl = options?.baseUrl ?? "https://gamma-api.polymarket.com";
  const proxyUrl = options?.proxyUrl;

  async function fetchWithProxy(url: string): Promise<Response> {
    const fetchOptions: RequestInit & { agent?: unknown } = {};
    
    if (proxyUrl) {
      fetchOptions.agent = new HttpsProxyAgent(proxyUrl);
    }

    return fetch(url, fetchOptions);
  }

  return {
    async getMarketData(marketId: string): Promise<PolymarketMarketData> {
      try {
        // Try to fetch from Gamma API
        const url = `${baseUrl}/markets/${marketId}`;
        const response = await fetchWithProxy(url);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = (await response.json()) as GammaMarketResponse;

        return {
          marketId: data.id,
          marketTitle: data.question,
          resolvesAt: new Date(data.resolution_date).getTime(),
          liquidity: parseFloat(data.liquidity) || 0,
          description: data.description,
          category: data.category,
          outcomes: data.outcomes,
        };
      } catch (error) {
        console.error(`[polymarket-api] Failed to fetch market ${marketId}:`, error);
        throw error;
      }
    },
  };
}

/**
 * Create a market metadata provider that uses real Polymarket API
 * Falls back to placeholder if API fails
 */
export function createPolymarketMarketMetadataProvider(options?: {
  proxyUrl?: string;
}): (marketId: string) => Promise<{
  marketId: string;
  marketTitle: string;
  resolvesAt: number;
  liquidity: number;
}> {
  const client = createPolymarketApiClient({ proxyUrl: options?.proxyUrl });

  return async (marketId: string) => {
    try {
      const data = await client.getMarketData(marketId);
      console.log(`[polymarket-api] Fetched real data for ${marketId}: ${data.marketTitle}`);
      return {
        marketId: data.marketId,
        marketTitle: data.marketTitle,
        resolvesAt: data.resolvesAt,
        liquidity: data.liquidity,
      };
    } catch (error) {
      // Fallback to placeholder on error
      console.warn(`[polymarket-api] Falling back to placeholder for ${marketId}`);
      return {
        marketId,
        marketTitle: marketId,
        resolvesAt: Date.now() + 86_400_000,
        liquidity: 10_000,
      };
    }
  };
}
