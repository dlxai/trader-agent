import { createRollingWindow } from "./rolling-window.js";
import type { RollingWindow, Trade, WindowStats } from "./rolling-window.js";

export interface MarketSnapshotInternal {
  window1m: WindowStats;
  window5m: WindowStats;
  currentMidPrice: number;
  lastTradeMs: number;
}

interface MarketEntry {
  window1m: RollingWindow;
  window5m: RollingWindow;
  currentMidPrice: number;
  lastTradeMs: number;
}

export interface MarketState {
  addTrade(marketId: string, trade: Trade): void;
  getSnapshot(marketId: string, nowMs: number): MarketSnapshotInternal | null;
  gc(nowMs: number): void;
}

export function createMarketState(opts: { idleGcMs: number }): MarketState {
  const markets = new Map<string, MarketEntry>();

  function getOrCreate(marketId: string): MarketEntry {
    let entry = markets.get(marketId);
    if (!entry) {
      entry = {
        window1m: createRollingWindow({ windowMs: 60_000 }),
        window5m: createRollingWindow({ windowMs: 300_000 }),
        currentMidPrice: 0,
        lastTradeMs: 0,
      };
      markets.set(marketId, entry);
    }
    return entry;
  }

  return {
    addTrade(marketId, trade) {
      const entry = getOrCreate(marketId);
      entry.window1m.add(trade);
      entry.window5m.add(trade);
      entry.currentMidPrice = trade.price;
      entry.lastTradeMs = trade.timestampMs;
    },
    getSnapshot(marketId, nowMs) {
      const entry = markets.get(marketId);
      if (!entry) return null;
      return {
        window1m: entry.window1m.stats(nowMs),
        window5m: entry.window5m.stats(nowMs),
        currentMidPrice: entry.currentMidPrice,
        lastTradeMs: entry.lastTradeMs,
      };
    },
    gc(nowMs) {
      const cutoff = nowMs - opts.idleGcMs;
      for (const [id, entry] of markets.entries()) {
        if (entry.lastTradeMs < cutoff) {
          markets.delete(id);
        }
      }
    },
  };
}
