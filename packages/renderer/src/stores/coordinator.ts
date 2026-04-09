import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

export interface Alert {
  severity: "critical" | "warning" | "info";
  text: string;
}

export interface CoordinatorBrief {
  summary: string;
  alerts: Alert[];
  suggestions: string[];
}

interface CoordinatorState {
  latestSummary: string;
  generatedMinutesAgo: number;
  latestAlerts: Alert[];
  latestSuggestions: string[];
  refresh: () => Promise<void>;
  setLatestBrief: (brief: CoordinatorBrief) => void;
}

// No mock data - only real data from backend
export const useCoordinator = create<CoordinatorState>((set) => ({
  latestSummary: "Waiting for coordinator data...",
  generatedMinutesAgo: 0,
  latestAlerts: [],
  latestSuggestions: [],
  refresh: async () => {
    if (!isElectron()) return;
    try {
      const brief = await pmt.getLatestCoordinatorBrief();
      if (!brief) return;
      set({
        latestSummary: brief.summary,
        generatedMinutesAgo: Math.floor(
          (Date.now() - brief.generated_at) / 60_000,
        ),
      });
    } catch (err) {
      console.error("[coordinator] Failed to refresh:", err);
    }
  },
  setLatestBrief: (brief) => {
    set({
      latestSummary: brief.summary,
      latestAlerts: brief.alerts,
      latestSuggestions: brief.suggestions,
      generatedMinutesAgo: 0,
    });
  },
}));
