import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

export interface ProviderInfoUI {
  id: string;
  name: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  authDetail?: string;
  models?: string[];
}

export interface AgentAssignment {
  providerId: string;
  modelId: string;
}

export interface PendingProposal {
  id: number;
  field: string;
  oldValue: string;
  proposedValue: string;
  rationale: string;
  sampleCount: number;
  expectedDeltaWinrate: number;
}

export interface Thresholds {
  minTradeUsdc: number;
  minNetFlow1m: number;
  minUniqueTraders1m: number;
  minPriceMove5m: number;
  minLiquidity: number;
  deadZoneMin: number;
  deadZoneMax: number;
}

export interface RiskLimits {
  totalCapital: number;
  maxPositionUsdc: number;
  maxSingleLoss: number;
  maxOpenPositions: number;
  dailyHaltPct: number;
  takeProfitPct: number;
  stopLossPct: number;
}

interface SettingsState {
  providers: ProviderInfoUI[];
  agentModels: Record<"analyzer" | "reviewer" | "risk_manager", AgentAssignment>;
  thresholds: Thresholds;
  riskLimits: RiskLimits;
  pendingProposals: PendingProposal[];
  loaded: boolean;
  refresh: () => Promise<void>;
  removeProposalLocally: (id: number) => void;
}

// Initial state seeded with M4 mock values so dev-mode (non-Electron) rendering
// and existing jsdom tests continue to show meaningful data. When running
// inside Electron, refresh() overwrites providers/pendingProposals with live
// IPC data. Thresholds/riskLimits remain mock until the config IPC is wired.
const INITIAL_PROVIDERS: ProviderInfoUI[] = [
  {
    id: "anthropic_api",
    name: "Anthropic",
    authType: "api_key",
    isConnected: true,
    authDetail: "sk-ant-...4f2a",
    models: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
  },
  { id: "deepseek", name: "DeepSeek", authType: "api_key", isConnected: false },
  { id: "zhipu", name: "Zhipu / Z.ai", authType: "api_key", isConnected: false },
  { id: "openai", name: "OpenAI", authType: "api_key", isConnected: false },
  {
    id: "anthropic_subscription",
    name: "Claude (Sub)",
    authType: "cli_credential",
    isConnected: true,
    authDetail: "Auto \u00B7 Max plan \u00B7 4d left",
  },
  {
    id: "gemini_oauth",
    name: "Gemini (OAuth)",
    authType: "oauth",
    isConnected: true,
    authDetail: "Free tier \u00B7 1000/day",
  },
];

const INITIAL_AGENT_MODELS: Record<
  "analyzer" | "reviewer" | "risk_manager",
  AgentAssignment
> = {
  analyzer: { providerId: "anthropic_subscription", modelId: "claude-opus-4-6" },
  reviewer: {
    providerId: "anthropic_subscription",
    modelId: "claude-sonnet-4-6",
  },
  risk_manager: { providerId: "gemini_oauth", modelId: "gemini-2.5-flash" },
};

const INITIAL_THRESHOLDS: Thresholds = {
  minTradeUsdc: 200,
  minNetFlow1m: 3500,
  minUniqueTraders1m: 3,
  minPriceMove5m: 0.03,
  minLiquidity: 5000,
  deadZoneMin: 0.6,
  deadZoneMax: 0.85,
};

const INITIAL_RISK_LIMITS: RiskLimits = {
  totalCapital: 10000,
  maxPositionUsdc: 300,
  maxSingleLoss: 50,
  maxOpenPositions: 8,
  dailyHaltPct: 0.02,
  takeProfitPct: 0.1,
  stopLossPct: 0.07,
};

const INITIAL_PROPOSALS: PendingProposal[] = [
  {
    id: 1,
    field: "min_unique_traders_1m",
    oldValue: "3",
    proposedValue: "4",
    rationale:
      "Bucket 0.40-0.60 win rate is 58% over 22 trades; tightening filter projected to lift to ~64%.",
    sampleCount: 22,
    expectedDeltaWinrate: 0.06,
  },
  {
    id: 2,
    field: "take_profit_pct",
    oldValue: "0.10",
    proposedValue: "0.08",
    rationale: "Past 30 trades show 70% of TP exits happen below +9%.",
    sampleCount: 30,
    expectedDeltaWinrate: 0.04,
  },
];

export const useSettings = create<SettingsState>((set) => ({
  providers: INITIAL_PROVIDERS,
  agentModels: INITIAL_AGENT_MODELS,
  thresholds: INITIAL_THRESHOLDS,
  riskLimits: INITIAL_RISK_LIMITS,
  pendingProposals: INITIAL_PROPOSALS,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    const [providers, proposals] = await Promise.all([
      pmt.listProviders(),
      pmt.getPendingProposals(),
      pmt.getConfig(),
    ]);
    set({
      providers: providers.map((p) => ({
        id: p.providerId,
        name: p.displayName,
        authType: p.authType,
        isConnected: p.isConnected,
        models: p.models.map((m) => m.id),
      })),
      pendingProposals: proposals.map((p) => ({
        id: p.proposal_id,
        field: p.field,
        oldValue: p.old_value,
        proposedValue: p.proposed_value,
        rationale: p.rationale,
        sampleCount: p.sample_count,
        expectedDeltaWinrate: p.expected_delta_winrate ?? 0,
      })),
      loaded: true,
    });
  },

  removeProposalLocally: (id) =>
    set((state) => ({
      pendingProposals: state.pendingProposals.filter((p) => p.id !== id),
    })),
}));
