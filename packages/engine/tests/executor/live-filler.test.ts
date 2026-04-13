import { describe, it, expect, vi } from "vitest";
import { createLiveFiller } from "../../src/executor/live-filler.js";
import type { ClobOrderService } from "../../src/executor/clob-order-service.js";

function mockClob(overrides: Partial<ClobOrderService> = {}): ClobOrderService {
  return {
    initialize: vi.fn().mockResolvedValue(undefined),
    getOrderBook: vi.fn().mockResolvedValue({ bestBid: 0.49, bestAsk: 0.51, midPrice: 0.50 }),
    placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: true, filledSize: 100 }),
    placeLimitOrder: vi.fn().mockResolvedValue({ orderId: "o2", filled: true, filledPrice: 0.50, filledSize: 100 }),
    cancelOrder: vi.fn().mockResolvedValue(undefined),
    cancelAll: vi.fn().mockResolvedValue(undefined),
    getUsdcBalance: vi.fn().mockResolvedValue(5000),
    ...overrides,
  };
}

const baseParams = {
  tokenId: "token-abc",
  midPrice: 0.50,
  sizeUsdc: 100,
  direction: "buy_yes" as const,
  timestampMs: Date.now(),
};

describe("LiveFiller - buy", () => {
  it("uses FOK market order when slippage within threshold", async () => {
    const clob = mockClob();
    const filler = createLiveFiller({ clob, slippageThreshold: 0.05, maxSlippage: 0.02, limitOrderTimeoutSec: 0 });

    const result = await filler.fillBuy(baseParams);

    expect(clob.placeMarketOrder).toHaveBeenCalledOnce();
    expect(result.filled).toBe(true);
    expect(result.reason).toBe("filled");
  });

  it("falls back to limit when FOK fails", async () => {
    const clob = mockClob({
      placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: false }),
    });
    const filler = createLiveFiller({ clob, slippageThreshold: 0.05, maxSlippage: 0.02, limitOrderTimeoutSec: 0 });

    const result = await filler.fillBuy(baseParams);

    expect(clob.placeMarketOrder).toHaveBeenCalledOnce();
    expect(clob.placeLimitOrder).toHaveBeenCalledOnce();
    expect(result.filled).toBe(true);
    expect(result.reason).toBe("filled");
  });

  it("rejects when balance insufficient", async () => {
    const clob = mockClob({
      getUsdcBalance: vi.fn().mockResolvedValue(10),
    });
    const filler = createLiveFiller({ clob, slippageThreshold: 0.05, maxSlippage: 0.02, limitOrderTimeoutSec: 0 });

    const result = await filler.fillBuy(baseParams);

    expect(result.filled).toBe(false);
    expect(result.reason).toBe("insufficient_balance");
    expect(clob.placeMarketOrder).not.toHaveBeenCalled();
  });
});

describe("LiveFiller - sell", () => {
  it("sell retries with aggressive prices on failure", async () => {
    const clob = mockClob({
      placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: false }),
      placeLimitOrder: vi.fn()
        .mockResolvedValueOnce({ orderId: "retry1", filled: false })
        .mockResolvedValueOnce({ orderId: "retry2", filled: true, filledPrice: 0.48 }),
    });
    const filler = createLiveFiller({ clob, slippageThreshold: 0.05, maxSlippage: 0.02, limitOrderTimeoutSec: 0 });

    const result = await filler.fillSell(baseParams);

    expect(clob.placeMarketOrder).toHaveBeenCalledOnce();
    expect(clob.placeLimitOrder).toHaveBeenCalledTimes(2);
    expect(result.filled).toBe(true);
    expect(result.reason).toBe("filled");
  });

  it("sell returns missed_fill after 3 retries fail", async () => {
    const clob = mockClob({
      placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: false }),
      placeLimitOrder: vi.fn().mockResolvedValue({ orderId: "retry", filled: false }),
    });
    const filler = createLiveFiller({ clob, slippageThreshold: 0.05, maxSlippage: 0.02, limitOrderTimeoutSec: 0 });

    const result = await filler.fillSell(baseParams);

    expect(clob.placeLimitOrder).toHaveBeenCalledTimes(3);
    expect(clob.cancelOrder).toHaveBeenCalledTimes(3);
    expect(result.filled).toBe(false);
    expect(result.reason).toBe("missed_fill");
  });
});
