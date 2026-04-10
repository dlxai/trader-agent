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
  updateThreshold: (key: keyof Thresholds, value: number) => Promise<void>;
  updateRiskLimit: (key: keyof RiskLimits, value: number) => Promise<void>;
  setAgentModel: (agentId: "analyzer" | "reviewer" | "risk_manager", providerId: string, modelId: string) => Promise<void>;
  connectProvider: (providerId: string, credentials: { apiKey?: string; baseUrl?: string }) => Promise<void>;
  disconnectProvider: (providerId: string) => Promise<void>;
}

// All available providers - shown in UI even when not connected
const INITIAL_PROVIDERS: ProviderInfoUI[] = [
  // API Key providers
  { id: "anthropic_api", name: "Anthropic", authType: "api_key", isConnected: false },
  { id: "openai", name: "OpenAI", authType: "api_key", isConnected: false },
  { id: "deepseek", name: "DeepSeek", authType: "api_key", isConnected: false },
  { id: "zhipu", name: "Zhipu / Z.ai", authType: "api_key", isConnected: false },
  { id: "gemini_api", name: "Gemini", authType: "api_key", isConnected: false },
  { id: "moonshot", name: "Moonshot", authType: "api_key", isConnected: false },
  { id: "qwen", name: "Qwen", authType: "api_key", isConnected: false },
  { id: "groq", name: "Groq", authType: "api_key", isConnected: false },
  { id: "mistral", name: "Mistral", authType: "api_key", isConnected: false },
  { id: "xai", name: "xAI", authType: "api_key", isConnected: false },
  // Local/CLI providers
  { id: "ollama", name: "Ollama", authType: "cli_credential", isConnected: false },
];

// Default proxy configuration - enabled by default with common proxy address
export const DEFAULT_PROXY_CONFIG = {
  enabled: true,
  httpProxy: "http://127.0.0.1:7890",
  httpsProxy: "http://127.0.0.1:7890",
};

const INITIAL_AGENT_MODELS: Record<
  "analyzer" | "reviewer" | "risk_manager",
  AgentAssignment
> = {
  analyzer: { providerId: "", modelId: "" },
  reviewer: { providerId: "", modelId: "" },
  risk_manager: { providerId: "", modelId: "" },
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

const INITIAL_PROPOSALS: PendingProposal[] = [];

export const useSettings = create<SettingsState>((set) => ({
  providers: INITIAL_PROVIDERS,
  agentModels: INITIAL_AGENT_MODELS,
  thresholds: INITIAL_THRESHOLDS,
  riskLimits: INITIAL_RISK_LIMITS,
  pendingProposals: INITIAL_PROPOSALS,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    try {
      const [providers, proposals, config] = await Promise.all([
        pmt.listProviders(),
        pmt.getPendingProposals(),
        pmt.getConfig(),
      ]);

    // Merge connected providers with initial provider list
    const connectedProviderMap = new Map(
      providers.map((p) => [
        p.providerId,
        {
          id: p.providerId,
          name: p.displayName,
          authType: p.authType,
          isConnected: p.isConnected,
          models: p.models.map((m) => m.id),
        },
      ])
    );

    // Merge: use connected provider data if available, otherwise use initial data
    const mergedProviders = INITIAL_PROVIDERS.map((initial) => {
      const connected = connectedProviderMap.get(initial.id);
      if (connected) {
        return connected;
      }
      return initial;
    });

    // Parse config and update thresholds/riskLimits if available
    const updates: Partial<SettingsState> = {
      providers: mergedProviders,
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
    };

    // Update thresholds from config if available
    if (config && typeof config === "object") {
      const cfg = config as Record<string, unknown>;
      if (cfg.minTradeUsdc !== undefined) {
        updates.thresholds = { ...INITIAL_THRESHOLDS, minTradeUsdc: Number(cfg.minTradeUsdc) };
      }
      if (cfg.minNetFlow1m !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), minNetFlow1m: Number(cfg.minNetFlow1m) };
      }
      if (cfg.minUniqueTraders1m !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), minUniqueTraders1m: Number(cfg.minUniqueTraders1m) };
      }
      if (cfg.minPriceMove5m !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), minPriceMove5m: Number(cfg.minPriceMove5m) };
      }
      if (cfg.minLiquidity !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), minLiquidity: Number(cfg.minLiquidity) };
      }
      if (cfg.deadZoneMin !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), deadZoneMin: Number(cfg.deadZoneMin) };
      }
      if (cfg.deadZoneMax !== undefined) {
        updates.thresholds = { ...(updates.thresholds || INITIAL_THRESHOLDS), deadZoneMax: Number(cfg.deadZoneMax) };
      }

      // Update risk limits from config
      if (cfg.totalCapital !== undefined) {
        updates.riskLimits = { ...INITIAL_RISK_LIMITS, totalCapital: Number(cfg.totalCapital) };
      }
      if (cfg.maxPositionUsdc !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), maxPositionUsdc: Number(cfg.maxPositionUsdc) };
      }
      if (cfg.maxSingleLoss !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), maxSingleLoss: Number(cfg.maxSingleLoss) };
      }
      if (cfg.maxOpenPositions !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), maxOpenPositions: Number(cfg.maxOpenPositions) };
      }
      if (cfg.dailyHaltPct !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), dailyHaltPct: Number(cfg.dailyHaltPct) };
      }
      if (cfg.takeProfitPct !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), takeProfitPct: Number(cfg.takeProfitPct) };
      }
      if (cfg.stopLossPct !== undefined) {
        updates.riskLimits = { ...(updates.riskLimits || INITIAL_RISK_LIMITS), stopLossPct: Number(cfg.stopLossPct) };
      }
    }

    set(updates);
    } catch (err) {
      console.error("[settings] refresh failed:", err);
    }
  },

  removeProposalLocally: (id) =>
    set((state) => ({
      pendingProposals: state.pendingProposals.filter((p) => p.id !== id),
    })),

  updateThreshold: async (key, value) => {
    if (isElectron()) {
      await pmt.updateConfigField(key, value);
    }
    set((state) => ({
      thresholds: { ...state.thresholds, [key]: value },
    }));
  },

  updateRiskLimit: async (key, value) => {
    if (isElectron()) {
      await pmt.updateConfigField(key, value);
    }
    set((state) => ({
      riskLimits: { ...state.riskLimits, [key]: value },
    }));
  },

  setAgentModel: async (agentId, providerId, modelId) => {
    if (isElectron()) {
      await pmt.setAgentModel(agentId, providerId, modelId);
    }
    set((state) => ({
      agentModels: { ...state.agentModels, [agentId]: { providerId, modelId } },
    }));
  },

  connectProvider: async (providerId, credentials) => {
    console.log("[settings store] connectProvider called:", providerId, "isElectron:", isElectron());
    if (isElectron()) {
      try {
        await pmt.connectProvider(providerId, credentials);
        console.log("[settings store] connectProvider succeeded");
        // Refresh providers list after connection
        await useSettings.getState().refresh();
        console.log("[settings store] providers refreshed");
      } catch (err) {
        console.error("[settings store] connectProvider failed:", err);
        throw err;
      }
    } else {
      console.warn("[settings store] Not in Electron, skipping connectProvider");
    }
  },

  disconnectProvider: async (providerId) => {
    if (isElectron()) {
      await pmt.disconnectProvider(providerId);
      // Refresh providers list after disconnection
      await useSettings.getState().refresh();
    }
  },
}));
