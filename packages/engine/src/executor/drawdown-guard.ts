import type { DrawdownGuardConfig } from "../config/schema.js";

export interface DrawdownGuard {
  onPriceTick(signalId: string, currentPnlPct: number): void;
  shouldExit(signalId: string, currentPnlPct: number): boolean;
  clear(signalId: string): void;
}

export function createDrawdownGuard(config: DrawdownGuardConfig): DrawdownGuard {
  const peakPnl = new Map<string, number>();

  return {
    onPriceTick(signalId, currentPnlPct) {
      if (!config.enabled) return;
      const prev = peakPnl.get(signalId) ?? -Infinity;
      if (currentPnlPct > prev) {
        peakPnl.set(signalId, currentPnlPct);
      }
    },
    shouldExit(signalId, currentPnlPct) {
      if (!config.enabled) return false;
      const peak = peakPnl.get(signalId);
      if (peak === undefined || peak <= 0) return false;
      if (currentPnlPct < config.minProfitPct) return false;
      const drawdown = (peak - currentPnlPct) / peak;
      return drawdown >= config.maxDrawdownFromPeak;
    },
    clear(signalId) {
      peakPnl.delete(signalId);
    },
  };
}
