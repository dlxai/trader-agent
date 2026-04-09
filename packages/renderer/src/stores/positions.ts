import { create } from "zustand";
import type { Position } from "../components/PositionTable.js";
import { pmt, isElectron, type OpenPosition } from "../ipc-client.js";

interface PositionsState {
  positions: Position[];
  loaded: boolean;
  refresh: () => Promise<void>;
}

function formatHeldDuration(triggeredAt: number): string {
  const ms = Date.now() - triggeredAt;
  const totalMin = Math.floor(ms / 60_000);
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${h}h ${m.toString().padStart(2, "0")}m`;
}

// No mock data - only real data from backend
export const usePositions = create<PositionsState>((set) => ({
  positions: [],
  loaded: false,
  refresh: async () => {
    if (!isElectron()) return;
    try {
      const rows = await pmt.getOpenPositions();
      const positions: Position[] = rows.map((r: OpenPosition) => ({
        signalId: r.signal_id,
        marketTitle: r.market_title,
        side: r.direction,
        entryPrice: r.entry_price,
        currentPrice: r.entry_price, // Will be updated with live price
        sizeUsdc: r.size_usdc,
        pnl: 0, // Will be computed with live price
        heldDuration: formatHeldDuration(r.triggered_at),
      }));
      set({ positions, loaded: true });
    } catch (err) {
      console.error("[positions] Failed to refresh:", err);
      set({ positions: [], loaded: true });
    }
  },
}));
