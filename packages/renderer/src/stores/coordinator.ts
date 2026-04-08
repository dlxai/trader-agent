import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

interface CoordinatorState {
  latestSummary: string;
  generatedMinutesAgo: number;
  refresh: () => Promise<void>;
}

// Initial state seeded with M4 mock values so dev-mode (non-Electron) rendering
// and existing jsdom tests continue to show meaningful data. When running inside
// Electron, refresh() overwrites these with live IPC data.
export const useCoordinator = create<CoordinatorState>((set) => ({
  latestSummary:
    "7 triggers detected in last hour, 2 entered. PnL +$8.34. Net flow on US Election markets unusually elevated \u2014 consider tightening unique_traders_1m to 4.",
  generatedMinutesAgo: 23,
  refresh: async () => {
    if (!isElectron()) return;
    const brief = await pmt.getLatestCoordinatorBrief();
    if (!brief) return;
    set({
      latestSummary: brief.summary,
      generatedMinutesAgo: Math.floor(
        (Date.now() - brief.generated_at) / 60_000,
      ),
    });
  },
}));
