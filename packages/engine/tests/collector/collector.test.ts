import { describe, it, expect, vi } from "vitest";
import { createCollector } from "../../src/collector/collector.js";
import { createEventBus } from "../../src/bus/events.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { TriggerEvent } from "../../src/bus/types.js";

describe("collector", () => {
  it("publishes a trigger event when a market meets all conditions", async () => {
    const bus = createEventBus();
    const received: TriggerEvent[] = [];
    bus.onTrigger((t) => received.push(t));

    const collector = createCollector({
      config: DEFAULT_CONFIG,
      bus,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      wsClientFactory: () => ({ connect: vi.fn().mockResolvedValue(undefined), close: vi.fn() }) as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      executor: { onPriceTick: vi.fn(), openPositions: vi.fn().mockReturnValue([]) } as any,
      marketMetadataProvider: async (marketId: string) => ({
        marketId,
        marketTitle: "Test market",
        resolvesAt: Date.now() + 7_200_000,
        liquidity: 6000,
      }),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });

    const now = Date.now();
    // Need 4 unique traders, net_flow >= 3000 in 1m, price move >= 3% in 5m, size >= $200 each
    // Note: trade size must be >= minTradeUsdc (default $200)
    const trades = [
      { marketId: "m1", address: "a", sizeUsdc: 1200, side: "buy" as const, price: 0.50, timestampMs: now - 280_000 },
      { marketId: "m1", address: "b", sizeUsdc: 1200, side: "buy" as const, price: 0.52, timestampMs: now - 40_000 },
      { marketId: "m1", address: "c", sizeUsdc: 1200, side: "buy" as const, price: 0.54, timestampMs: now - 20_000 },
      { marketId: "m1", address: "d", sizeUsdc: 1200, side: "buy" as const, price: 0.55, timestampMs: now },
    ];
    for (const t of trades) await collector.ingestTrade(t);

    expect(received).toHaveLength(1);
    expect(received[0]?.market_id).toBe("m1");
    expect(received[0]?.direction).toBe("buy_yes");
  });

  it("publishes no trigger when net flow is insufficient", async () => {
    const bus = createEventBus();
    const received: TriggerEvent[] = [];
    bus.onTrigger((t) => received.push(t));

    const collector = createCollector({
      config: DEFAULT_CONFIG,
      bus,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      wsClientFactory: () => ({ connect: vi.fn().mockResolvedValue(undefined), close: vi.fn() }) as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      executor: { onPriceTick: vi.fn(), openPositions: vi.fn().mockReturnValue([]) } as any,
      marketMetadataProvider: async (marketId) => ({
        marketId,
        marketTitle: "Test market",
        resolvesAt: Date.now() + 7_200_000,
        liquidity: 6000,
      }),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });

    const now = Date.now();
    await collector.ingestTrade({
      marketId: "m1",
      address: "a",
      sizeUsdc: 300,
      side: "buy",
      price: 0.55,
      timestampMs: now,
    });
    expect(received).toHaveLength(0);
  });

  it("filters out trades smaller than minTradeUsdc", async () => {
    const bus = createEventBus();
    const received: TriggerEvent[] = [];
    bus.onTrigger((t) => received.push(t));

    const collector = createCollector({
      config: DEFAULT_CONFIG,
      bus,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      wsClientFactory: () => ({ connect: vi.fn().mockResolvedValue(undefined), close: vi.fn() }) as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      executor: { onPriceTick: vi.fn(), openPositions: vi.fn().mockReturnValue([]) } as any,
      marketMetadataProvider: async (marketId) => ({
        marketId,
        marketTitle: "Test market",
        resolvesAt: Date.now() + 7_200_000,
        liquidity: 6000,
      }),
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });

    await collector.ingestTrade({
      marketId: "m1",
      address: "a",
      sizeUsdc: 50,
      side: "buy",
      price: 0.55,
      timestampMs: Date.now(),
    });
    expect(received).toHaveLength(0);
  });
});
