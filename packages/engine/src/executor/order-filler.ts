export interface FillParams {
  tokenId: string;
  midPrice: number;
  sizeUsdc: number;
  direction: "buy_yes" | "buy_no";
  timestampMs: number;
}

export interface FillResult {
  filled: boolean;
  fillPrice: number;
  filledSize: number;
  orderId?: string;
  reason: "filled" | "partial" | "missed_fill" | "insufficient_balance";
}

export interface OrderFiller {
  fillBuy(params: FillParams): Promise<FillResult>;
  fillSell(params: FillParams): Promise<FillResult>;
}
