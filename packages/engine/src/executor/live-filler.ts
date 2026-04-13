import type { OrderFiller, FillParams, FillResult } from "./order-filler.js";
import type { ClobOrderService } from "./clob-order-service.js";

export interface LiveFillerConfig {
  clob: ClobOrderService;
  slippageThreshold: number;
  maxSlippage: number;
  limitOrderTimeoutSec: number;
}

export function createLiveFiller(config: LiveFillerConfig): OrderFiller {
  async function executeBuy(params: FillParams): Promise<FillResult> {
    const balance = await config.clob.getUsdcBalance();
    if (balance < params.sizeUsdc) {
      return { filled: false, fillPrice: 0, filledSize: 0, reason: "insufficient_balance" };
    }
    const book = await config.clob.getOrderBook(params.tokenId);
    const deviation = Math.abs(book.bestAsk - params.midPrice) / params.midPrice;

    if (deviation <= config.slippageThreshold) {
      const result = await config.clob.placeMarketOrder({ tokenId: params.tokenId, side: "BUY", amount: params.sizeUsdc });
      if (result.filled) {
        return { filled: true, fillPrice: result.filledPrice ?? book.bestAsk, filledSize: params.sizeUsdc, orderId: result.orderId, reason: "filled" };
      }
    }

    const limitPrice = Math.min(params.midPrice * (1 + config.maxSlippage), book.bestAsk);
    const shares = params.sizeUsdc / limitPrice;
    const limitResult = await config.clob.placeLimitOrder({ tokenId: params.tokenId, side: "BUY", price: limitPrice, size: shares });

    if (config.limitOrderTimeoutSec > 0) {
      await new Promise((r) => setTimeout(r, config.limitOrderTimeoutSec * 1000));
    }

    if (limitResult.filled) {
      return { filled: true, fillPrice: limitPrice, filledSize: params.sizeUsdc, orderId: limitResult.orderId, reason: "filled" };
    }

    if (limitResult.orderId) {
      await config.clob.cancelOrder(limitResult.orderId).catch(() => {});
    }
    return { filled: false, fillPrice: 0, filledSize: 0, reason: "missed_fill" };
  }

  async function executeSell(params: FillParams): Promise<FillResult> {
    const book = await config.clob.getOrderBook(params.tokenId);
    const result = await config.clob.placeMarketOrder({ tokenId: params.tokenId, side: "SELL", amount: params.sizeUsdc / params.midPrice });
    if (result.filled) {
      return { filled: true, fillPrice: result.filledPrice ?? book.bestBid, filledSize: params.sizeUsdc, orderId: result.orderId, reason: "filled" };
    }

    const tickSize = 0.01;
    for (let retry = 1; retry <= 3; retry++) {
      const aggressivePrice = book.bestBid - tickSize * (retry === 3 ? 5 : retry);
      const shares = params.sizeUsdc / params.midPrice;
      const retryResult = await config.clob.placeLimitOrder({ tokenId: params.tokenId, side: "SELL", price: Math.max(aggressivePrice, 0.001), size: shares });
      if (retryResult.filled) {
        return { filled: true, fillPrice: aggressivePrice, filledSize: params.sizeUsdc, orderId: retryResult.orderId, reason: "filled" };
      }
      if (retryResult.orderId) {
        await config.clob.cancelOrder(retryResult.orderId).catch(() => {});
      }
    }
    return { filled: false, fillPrice: 0, filledSize: 0, reason: "missed_fill" };
  }

  return { fillBuy: executeBuy, fillSell: executeSell };
}
