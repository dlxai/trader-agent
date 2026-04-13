export interface ClobOrderServiceConfig {
  privateKey: string;
  funderAddress: string;
  chainId: number;
  clobUrl?: string;
}

export interface ClobOrderResult {
  orderId: string;
  filled: boolean;
  filledPrice?: number;
  filledSize?: number;
}

export interface OrderBookSnapshot {
  bestBid: number;
  bestAsk: number;
  midPrice: number;
}

export interface ClobOrderService {
  initialize(): Promise<void>;
  getUsdcBalance(): Promise<number>;
  placeMarketOrder(params: { tokenId: string; side: "BUY" | "SELL"; amount: number }): Promise<ClobOrderResult>;
  placeLimitOrder(params: { tokenId: string; side: "BUY" | "SELL"; price: number; size: number }): Promise<ClobOrderResult>;
  cancelOrder(orderId: string): Promise<void>;
  cancelAll(): Promise<void>;
  getOrderBook(tokenId: string): Promise<OrderBookSnapshot>;
}
