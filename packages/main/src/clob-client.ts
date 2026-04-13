/**
 * Real ClobOrderService implementation using @polymarket/clob-client-v2.
 *
 * Wraps the Polymarket CLOB v2 client to implement the ClobOrderService
 * interface defined in @pmt/engine. Supports proxy wallet (POLY_PROXY)
 * authentication mode.
 */
import { ClobClient, SignatureTypeV2, OrderType, Side } from "@polymarket/clob-client-v2";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { polygon } from "viem/chains";
import type {
  ClobOrderService,
  ClobOrderServiceConfig,
  ClobOrderResult,
  OrderBookSnapshot,
} from "@pmt/engine";

export function createClobOrderService(config: ClobOrderServiceConfig): ClobOrderService {
  const account = privateKeyToAccount(config.privateKey as `0x${string}`);
  const walletClient = createWalletClient({
    account,
    chain: polygon,
    transport: http(),
  });

  const client = new ClobClient({
    host: config.clobUrl ?? "https://clob.polymarket.com",
    chain: config.chainId as 137,
    signer: walletClient,
    signatureType: SignatureTypeV2.POLY_PROXY,
    funderAddress: config.funderAddress,
  });

  let initialized = false;

  return {
    async initialize(): Promise<void> {
      if (initialized) return;
      const creds = await client.createOrDeriveApiKey();
      // Reconstruct client with credentials by setting them directly
      (client as any).creds = creds;
      initialized = true;
    },

    async getUsdcBalance(): Promise<number> {
      const result = await client.getBalanceAllowance({
        asset_type: "COLLATERAL" as any,
      });
      return parseFloat(result.balance ?? "0");
    },

    async placeMarketOrder(params): Promise<ClobOrderResult> {
      if (!initialized) await this.initialize();
      try {
        const resp = await client.createAndPostMarketOrder(
          {
            tokenID: params.tokenId,
            amount: params.amount,
            side: params.side === "BUY" ? Side.BUY : Side.SELL,
          },
          undefined,
          OrderType.FOK,
        );
        const price = resp?.takingAmount && resp?.makingAmount
          ? parseFloat(resp.takingAmount) / parseFloat(resp.makingAmount)
          : undefined;
        const result: ClobOrderResult = {
          orderId: resp?.orderID ?? "",
          filled: resp?.status === "matched" || resp?.status === "MATCHED",
          filledSize: params.amount,
        };
        if (price !== undefined) result.filledPrice = price;
        return result;
      } catch (err) {
        return { orderId: "", filled: false };
      }
    },

    async placeLimitOrder(params): Promise<ClobOrderResult> {
      if (!initialized) await this.initialize();
      try {
        const resp = await client.createAndPostOrder(
          {
            tokenID: params.tokenId,
            price: params.price,
            size: params.size,
            side: params.side === "BUY" ? Side.BUY : Side.SELL,
          },
          undefined,
          OrderType.GTC,
        );
        return {
          orderId: resp?.orderID ?? "",
          filled: resp?.status === "matched" || resp?.status === "MATCHED",
          filledPrice: params.price,
          filledSize: params.size,
        };
      } catch (err) {
        return { orderId: "", filled: false };
      }
    },

    async cancelOrder(orderId): Promise<void> {
      await client.cancelOrder({ orderID: orderId });
    },

    async cancelAll(): Promise<void> {
      await client.cancelAll();
    },

    async getOrderBook(tokenId): Promise<OrderBookSnapshot> {
      const book = await client.getOrderBook(tokenId);
      const bestBid = book.bids?.[0]?.price ? parseFloat(String(book.bids[0].price)) : 0;
      const bestAsk = book.asks?.[0]?.price ? parseFloat(String(book.asks[0].price)) : 1;
      return {
        bestBid,
        bestAsk,
        midPrice: (bestBid + bestAsk) / 2,
      };
    },
  };
}
