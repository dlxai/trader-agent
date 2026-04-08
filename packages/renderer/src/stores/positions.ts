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

// Initial state seeded with M4 mock values so dev-mode (non-Electron) rendering
// and existing jsdom tests continue to show meaningful data. When running inside
// Electron, refresh() overwrites these with live IPC data.
const INITIAL_POSITIONS: Position[] = [
  {
    signalId: "s1",
    marketTitle: "Trump approval > 50% by May",
    side: "buy_yes",
    entryPrice: 0.452,
    currentPrice: 0.481,
    sizeUsdc: 125,
    pnl: 8.02,
    heldDuration: "42m",
  },
  {
    signalId: "s2",
    marketTitle: "BTC > $100k by Apr 10",
    side: "buy_yes",
    entryPrice: 0.52,
    currentPrice: 0.508,
    sizeUsdc: 108,
    pnl: -2.49,
    heldDuration: "1h 18m",
  },
  {
    signalId: "s3",
    marketTitle: "Lakers vs Celtics tonight",
    side: "buy_no",
    entryPrice: 0.38,
    currentPrice: 0.395,
    sizeUsdc: 109,
    pnl: 3.81,
    heldDuration: "2h 04m",
  },
];

export const usePositions = create<PositionsState>((set) => ({
  positions: INITIAL_POSITIONS,
  loaded: false,
  refresh: async () => {
    if (!isElectron()) return;
    const rows = await pmt.getOpenPositions();
    const positions: Position[] = rows.map((r: OpenPosition) => ({
      signalId: r.signal_id,
      marketTitle: r.market_title,
      side: r.direction,
      entryPrice: r.entry_price,
      currentPrice: r.entry_price, // M6+ will track current_mid_price separately
      sizeUsdc: r.size_usdc,
      pnl: 0, // M6+ will compute live PnL
      heldDuration: formatHeldDuration(r.triggered_at),
    }));
    set({ positions, loaded: true });
  },
}));
