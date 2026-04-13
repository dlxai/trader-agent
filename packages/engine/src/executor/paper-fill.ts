import type { OrderFiller, FillParams, FillResult } from "./order-filler.js";

export interface PaperFillOptions {
  slippagePct: number;
}

export function createPaperFiller(opts: PaperFillOptions): OrderFiller {
  return {
    async fillBuy(params: FillParams): Promise<FillResult> {
      return {
        filled: true,
        fillPrice: params.midPrice * (1 + opts.slippagePct),
        filledSize: params.sizeUsdc,
        reason: "filled",
      };
    },
    async fillSell(params: FillParams): Promise<FillResult> {
      return {
        filled: true,
        fillPrice: params.midPrice * (1 - opts.slippagePct),
        filledSize: params.sizeUsdc,
        reason: "filled",
      };
    },
  };
}
