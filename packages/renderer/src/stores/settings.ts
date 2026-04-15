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

export interface LiveTradeSettings {
  mode: "paper" | "live";
  slippageThreshold: number;
  maxSlippage: number;
  limitOrderTimeoutSec: number;
}

export interface AiExitSettings {
  enabled: boolean;
  intervalSec: number;
}

export interface DrawdownGuardSettings {
  enabled: boolean;
  minProfitPct: number;
  maxDrawdownFromPeak: number;
}

export interface CoordinatorSettings {
  actionable: boolean;
  intervalMin: number;
}

export interface CustomEndpointInfo {
  id: string;
  displayName: string;
  baseUrl: string;
  modelName: string;
}

interface SettingsState {
  providers: ProviderInfoUI[];
  agentModels: Record<"analyzer" | "reviewer" | "risk_manager" | "position_evaluator", AgentAssignment>;
  thresholds: Thresholds;
  riskLimits: RiskLimits;
  liveTradeSettings: LiveTradeSettings;
  aiExitSettings: AiExitSettings;
  drawdownGuardSettings: DrawdownGuardSettings;
  coordinatorSettings: CoordinatorSettings;
  customEndpoints: CustomEndpointInfo[];
  pendingProposals: PendingProposal[];
  loaded: boolean;
  refresh: () => Promise<void>;
  removeProposalLocally: (id: number) => void;
  updateThreshold: (key: keyof Thresholds, value: number) => Promise<void>;
  updateRiskLimit: (key: keyof RiskLimits, value: number) => Promise<void>;
  setAgentModel: (agentId: "analyzer" | "reviewer" | "risk_manager" | "position_evaluator", providerId: string, modelId: string) => Promise<void>;
  connectProvider: (providerId: string, credentials: { apiKey?: string; baseUrl?: string }) => Promise<void>;
  disconnectProvider: (providerId: string) => Promise<void>;
  updateLiveTradeSettings: (settings: Partial<LiveTradeSettings>) => Promise<void>;
  updateAiExitSettings: (settings: Partial<AiExitSettings>) => Promise<void>;
  updateDrawdownGuardSettings: (settings: Partial<DrawdownGuardSettings>) => Promise<void>;
  updateCoordinatorSettings: (settings: Partial<CoordinatorSettings>) => Promise<void>;
  addCustomEndpoint: (input: { displayName: string; baseUrl: string; apiKey?: string; modelName: string }) => Promise<void>;
  removeCustomEndpoint: (id: string) => Promise<void>;
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
  // Subscription / Coding Plan providers (use api_key so users can enter tokens directly)
  { id: "anthropic_subscription", name: "Anthropic (Subscription)", authType: "api_key", isConnected: false },
  { id: "gemini_oauth", name: "Gemini (OAuth)", authType: "oauth", isConnected: false },
  { id: "zhipu_coding", name: "Zhipu (Coding Plan)", authType: "api_key", isConnected: false },
  { id: "qwen_coding", name: "Qwen (Coding Plan)", authType: "api_key", isConnected: false },
  { id: "kimi_code", name: "Kimi (Code Plan)", authType: "api_key", isConnected: false },
  { id: "minimax_coding", name: "MiniMax (Coding Plan)", authType: "api_key", isConnected: false },
  { id: "volcengine_coding", name: "Volcengine (Coding Plan)", authType: "api_key", isConnected: false },
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
  "analyzer" | "reviewer" | "risk_manager" | "position_evaluator",
  AgentAssignment
> = {
  analyzer: { providerId: "", modelId: "" },
  reviewer: { providerId: "", modelId: "" },
  risk_manager: { providerId: "", modelId: "" },
  position_evaluator: { providerId: "", modelId: "" },
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

const INITIAL_LIVE_TRADE: LiveTradeSettings = {
  mode: "paper",
  slippageThreshold: 0.02,
  maxSlippage: 0.03,
  limitOrderTimeoutSec: 60,
};

const INITIAL_AI_EXIT: AiExitSettings = {
  enabled: true,
  intervalSec: 180,
};

const INITIAL_DRAWDOWN_GUARD: DrawdownGuardSettings = {
  enabled: true,
  minProfitPct: 0.05,
  maxDrawdownFromPeak: 0.40,
};

const INITIAL_COORDINATOR: CoordinatorSettings = {
  actionable: true,
  intervalMin: 30,
};

export const useSettings = create<SettingsState>((set) => ({
  providers: INITIAL_PROVIDERS,
  agentModels: INITIAL_AGENT_MODELS,
  thresholds: INITIAL_THRESHOLDS,
  riskLimits: INITIAL_RISK_LIMITS,
  liveTradeSettings: INITIAL_LIVE_TRADE,
  aiExitSettings: INITIAL_AI_EXIT,
  drawdownGuardSettings: INITIAL_DRAWDOWN_GUARD,
  coordinatorSettings: INITIAL_COORDINATOR,
  customEndpoints: [],
  pendingProposals: INITIAL_PROPOSALS,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    try {
      const [providers, proposals, config, liveTradeConfig, aiExitConfig, drawdownGuardConfig, coordinatorConfig, customEndpoints] = await Promise.all([
        pmt.listProviders(),
        pmt.getPendingProposals(),
        pmt.getConfig(),
        pmt.getLiveTradeConfig(),
        pmt.getAiExitConfig(),
        pmt.getDrawdownGuardConfig(),
        pmt.getCoordinatorConfig(),
        pmt.listCustomEndpoints(),
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

    // Update new configs
    updates.liveTradeSettings = liveTradeConfig as LiveTradeSettings;
    updates.aiExitSettings = aiExitConfig as AiExitSettings;
    updates.drawdownGuardSettings = drawdownGuardConfig as DrawdownGuardSettings;
    updates.coordinatorSettings = coordinatorConfig as CoordinatorSettings;
    updates.customEndpoints = customEndpoints as CustomEndpointInfo[];

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
    console.log("[settings store] connectProvider called:", providerId, "credentials:", credentials, "isElectron:", isElectron());
    if (isElectron()) {
      try {
        console.log("[settings store] calling pmt.connectProvider...");
        const result = await pmt.connectProvider(providerId, credentials);
        console.log("[settings store] connectProvider result:", result);
        console.log("[settings store] refreshing providers...");
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

  updateLiveTradeSettings: async (settings) => {
    set((state) => {
      const updated = { ...state.liveTradeSettings, ...settings };
      if (isElectron()) {
        void pmt.setLiveTradeConfig(updated);
      }
      return { liveTradeSettings: updated };
    });
  },

  updateAiExitSettings: async (settings) => {
    set((state) => {
      const updated = { ...state.aiExitSettings, ...settings };
      if (isElectron()) {
        void pmt.setAiExitConfig(updated);
      }
      return { aiExitSettings: updated };
    });
  },

  updateDrawdownGuardSettings: async (settings) => {
    set((state) => {
      const updated = { ...state.drawdownGuardSettings, ...settings };
      if (isElectron()) {
        void pmt.setDrawdownGuardConfig(updated);
      }
      return { drawdownGuardSettings: updated };
    });
  },

  updateCoordinatorSettings: async (settings) => {
    set((state) => {
      const updated = { ...state.coordinatorSettings, ...settings };
      if (isElectron()) {
        void pmt.setCoordinatorConfig(updated);
      }
      return { coordinatorSettings: updated };
    });
  },

  addCustomEndpoint: async (input) => {
    if (isElectron()) {
      await pmt.addCustomEndpoint(input);
      await useSettings.getState().refresh();
    }
  },

  removeCustomEndpoint: async (id) => {
    if (isElectron()) {
      await pmt.removeCustomEndpoint(id);
      await useSettings.getState().refresh();
    }
  },
}));
