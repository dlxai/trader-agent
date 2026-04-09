import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

export interface PortfolioStoreState {
  equity: number;
  todayPnl: number;
  weeklyWinRate: number;
  weeklyWins: number;
  weeklyTotal: number;
  drawdownPct: number;
  peakEquity: number;
  openPositionCount: number;
  maxOpenPositions: number;
  totalExposure: number;
  loaded: boolean;
  refresh: () => Promise<void>;
}

// No mock data - only real data from backend
export const usePortfolio = create<PortfolioStoreState>((set) => ({
  equity: 0,
  todayPnl: 0,
  weeklyWinRate: 0,
  weeklyWins: 0,
  weeklyTotal: 0,
  drawdownPct: 0,
  peakEquity: 0,
  openPositionCount: 0,
  maxOpenPositions: 8,
  totalExposure: 0,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    try {
      const state = await pmt.getPortfolioState();
      if (!state) {
        set({ loaded: true });
        return;
      }
      const positions = await pmt.getOpenPositions();
      const closedSinceWeekStart = await pmt.getRecentClosedTrades(100);
      const wins = closedSinceWeekStart.filter(
        (t) => ((t as { pnl_net_usdc?: number }).pnl_net_usdc ?? 0) > 0,
      ).length;
      const totalExposure = positions.reduce(
        (sum, p) => sum + (p.size_usdc ?? 0),
        0,
      );
      const drawdownPct =
        state.peak_equity > 0
          ? -((state.peak_equity - state.current_equity) / state.peak_equity) * 100
          : 0;
      set({
        equity: state.current_equity ?? 0,
        todayPnl: (state.current_equity ?? 0) - (state.day_start_equity ?? 0),
        weeklyWinRate:
          closedSinceWeekStart.length > 0
            ? wins / closedSinceWeekStart.length
            : 0,
        weeklyWins: wins,
        weeklyTotal: closedSinceWeekStart.length,
        drawdownPct,
        peakEquity: state.peak_equity ?? 0,
        openPositionCount: positions.length,
        maxOpenPositions: 8,
        totalExposure,
        loaded: true,
      });
    } catch (err) {
      console.error("[portfolio] Failed to refresh:", err);
      set({ loaded: true });
    }
  },
}));
