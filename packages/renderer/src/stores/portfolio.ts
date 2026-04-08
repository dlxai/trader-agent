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

// Initial state seeded with M4 mock values so dev-mode (non-Electron) rendering
// and existing jsdom tests continue to show meaningful data. When running inside
// Electron, refresh() overwrites these with live IPC data.
export const usePortfolio = create<PortfolioStoreState>((set) => ({
  equity: 10127.5,
  todayPnl: 127.5,
  weeklyWinRate: 0.625,
  weeklyWins: 15,
  weeklyTotal: 24,
  drawdownPct: -1.2,
  peakEquity: 10250,
  openPositionCount: 3,
  maxOpenPositions: 8,
  totalExposure: 342,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    const state = await pmt.getPortfolioState();
    if (!state) return;
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
      equity: state.current_equity,
      todayPnl: state.current_equity - state.day_start_equity,
      weeklyWinRate:
        closedSinceWeekStart.length > 0
          ? wins / closedSinceWeekStart.length
          : 0,
      weeklyWins: wins,
      weeklyTotal: closedSinceWeekStart.length,
      drawdownPct,
      peakEquity: state.peak_equity,
      openPositionCount: positions.length,
      maxOpenPositions: 8,
      totalExposure,
      loaded: true,
    });
  },
}));
