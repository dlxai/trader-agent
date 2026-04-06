export interface PaperFillOptions {
  slippagePct: number;
}

export interface PaperFillRequest {
  midPrice: number;
  sizeUsdc: number;
  timestampMs: number;
}

export interface PaperFillResult {
  fillPrice: number;
  sizeUsdc: number;
  timestampMs: number;
}

export interface PaperFiller {
  fillBuy(req: PaperFillRequest): PaperFillResult;
  fillSell(req: PaperFillRequest): PaperFillResult;
}

export function createPaperFiller(opts: PaperFillOptions): PaperFiller {
  return {
    fillBuy(req) {
      return {
        fillPrice: req.midPrice * (1 + opts.slippagePct),
        sizeUsdc: req.sizeUsdc,
        timestampMs: req.timestampMs,
      };
    },
    fillSell(req) {
      return {
        fillPrice: req.midPrice * (1 - opts.slippagePct),
        sizeUsdc: req.sizeUsdc,
        timestampMs: req.timestampMs,
      };
    },
  };
}
