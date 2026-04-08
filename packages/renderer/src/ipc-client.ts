// Typed wrapper around window.pmt exposed by preload.ts.
// Renderer code imports from this module instead of touching window.* directly.

export interface PortfolioState {
  total_capital: number;
  current_equity: number;
  day_start_equity: number;
  week_start_equity: number;
  peak_equity: number;
  current_drawdown: number;
  daily_halt_triggered: boolean;
  weekly_halt_triggered: boolean;
}

export interface OpenPosition {
  signal_id: string;
  market_id: string;
  market_title: string;
  direction: "buy_yes" | "buy_no";
  entry_price: number;
  size_usdc: number;
  triggered_at: number;
}

export interface ProviderInfo {
  providerId: string;
  displayName: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  models: Array<{ id: string; contextWindow: number }>;
}

export interface FilterProposalRow {
  proposal_id: number;
  field: string;
  old_value: string;
  proposed_value: string;
  rationale: string;
  sample_count: number;
  expected_delta_winrate: number | null;
  status: "pending" | "approved" | "rejected";
}

export interface CoordinatorLogRow {
  log_id: number;
  generated_at: number;
  summary: string;
  alerts: string; // JSON string
  suggestions: string; // JSON string
}

declare global {
  interface Window {
    pmt: {
      getPortfolioState(): Promise<PortfolioState | null>;
      getOpenPositions(): Promise<OpenPosition[]>;
      getRecentClosedTrades(limit: number): Promise<unknown[]>;
      getLatestCoordinatorBrief(): Promise<CoordinatorLogRow | null>;
      triggerCoordinatorNow(): Promise<unknown>;
      getRecentReports(
        limit: number,
      ): Promise<Array<{ path: string; date: string; mtime: number }>>;
      getReportContent(path: string): Promise<string>;
      triggerReviewerNow(): Promise<unknown>;
      getPendingProposals(): Promise<FilterProposalRow[]>;
      approveProposal(id: number): Promise<void>;
      rejectProposal(id: number): Promise<void>;
      getConfig(): Promise<unknown>;
      updateConfigField(key: string, value: unknown): Promise<void>;
      listProviders(): Promise<ProviderInfo[]>;
      connectProvider(providerId: string, credentials: unknown): Promise<void>;
      disconnectProvider(providerId: string): Promise<void>;
      setAgentModel(
        agentId: string,
        providerId: string,
        modelId: string,
      ): Promise<void>;
      getChatHistory(agentId: string, limit: number): Promise<unknown[]>;
      sendMessage(agentId: string, content: string): Promise<{ content: string }>;
      sendMessageStream(agentId: string, content: string): Promise<{ content: string }>;
      clearChatHistory(agentId: string): Promise<void>;
      pauseTrading(): Promise<void>;
      resumeTrading(): Promise<void>;
      emergencyStop(): Promise<void>;
      rollbackAutoApply(historyId: number): Promise<{ success: boolean }>;
      getAutoApplyHistory(limit?: number): Promise<unknown[]>;
      getProxyConfig(): Promise<{ enabled: boolean; httpProxy: string; httpsProxy: string }>;
      setProxyConfig(config: { enabled: boolean; httpProxy: string; httpsProxy: string }): Promise<{ success: boolean }>;
      on(event: string, handler: (...args: unknown[]) => void): () => void;
    };
  }
}

export const pmt = (typeof window !== "undefined"
  ? window.pmt
  : undefined) as Window["pmt"];

export function isElectron(): boolean {
  return typeof window !== "undefined" && Boolean(window.pmt);
}
