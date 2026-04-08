/**
 * IPC handler registration for the Electron main process.
 *
 * M5.1 introduces the skeleton — every request/response channel the renderer
 * needs is registered up front with a stub body. Subsequent M5 tasks replace
 * the stubs with real implementations:
 *   - M5.4 wires provider connect through the secrets store
 *   - M5.6 wires scheduler triggers
 *   - M5.7 lists reports from the filesystem
 *   - M5.8 applies filter proposals to filter_config
 *   - M5.9 streams chat messages through the risk-manager runner
 *   - M5.10 force-closes positions during emergency stop
 *
 * The module is intentionally side-effect free at import time: handlers are
 * only registered when `registerIpcHandlers` is called from `onReady()`.
 */
import { ipcMain } from "electron";
import type { EngineContext } from "./lifecycle.js";
import type { RiskMgrRunner } from "@pmt/llm";

export interface IpcDeps {
  getEngineContext: () => EngineContext | null;
  getRiskMgrRunner: () => RiskMgrRunner | null;
}

export function registerIpcHandlers(deps: IpcDeps): void {
  // Portfolio
  ipcMain.handle("getPortfolioState", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    const rows = ctx.db
      .prepare("SELECT key, value FROM portfolio_state")
      .all() as Array<{ key: string; value: string }>;
    return Object.fromEntries(rows.map((r) => [r.key, JSON.parse(r.value)]));
  });

  ipcMain.handle("getOpenPositions", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare("SELECT * FROM signal_log WHERE exit_at IS NULL")
      .all();
  });

  ipcMain.handle("getRecentClosedTrades", async (_e, limit: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare(
        "SELECT * FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT ?"
      )
      .all(limit);
  });

  // Coordinator
  ipcMain.handle("getLatestCoordinatorBrief", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    return ctx.db
      .prepare(
        "SELECT * FROM coordinator_log ORDER BY generated_at DESC LIMIT 1"
      )
      .get();
  });

  ipcMain.handle("triggerCoordinatorNow", async () => {
    // M5.6 will wire this to the scheduler.triggerNow()
    return null;
  });

  // Reports
  ipcMain.handle("getRecentReports", async (_e, _limit: number) => {
    // M5.7 will list reports from filesystem
    return [];
  });

  ipcMain.handle("getReportContent", async (_e, _reportPath: string) => {
    // M5.7
    return "";
  });

  ipcMain.handle("triggerReviewerNow", async () => {
    // M5.6
    return null;
  });

  // Filter proposals
  ipcMain.handle("getPendingProposals", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare(
        "SELECT * FROM filter_proposals WHERE status = 'pending' ORDER BY created_at DESC"
      )
      .all();
  });

  ipcMain.handle("approveProposal", async (_e, id: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    // M5.8 will apply the proposal to filter_config and mark approved
    ctx.db
      .prepare(
        "UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?"
      )
      .run(Date.now(), id);
  });

  ipcMain.handle("rejectProposal", async (_e, id: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db
      .prepare(
        "UPDATE filter_proposals SET status = 'rejected', reviewed_at = ? WHERE proposal_id = ?"
      )
      .run(Date.now(), id);
  });

  // Config
  ipcMain.handle("getConfig", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    return ctx.config;
  });

  ipcMain.handle(
    "updateConfigField",
    async (_e, key: string, value: unknown) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");
      ctx.db
        .prepare(
          "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
        )
        .run(key, JSON.stringify(value), Date.now(), "user");
    }
  );

  // LLM Providers
  ipcMain.handle("listProviders", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.registry.list().map((p) => ({
      providerId: p.id,
      displayName: p.displayName,
      authType: p.authType,
      isConnected: p.isConnected(),
      models: p.listModels(),
    }));
  });

  ipcMain.handle(
    "connectProvider",
    async (
      _e,
      providerId: string,
      credentials: { apiKey?: string; baseUrl?: string }
    ) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");

      // Lazy import inside handler to avoid loading all SDKs at boot
      const {
        createOpenAICompatProvider,
        createAnthropicProvider,
        createGeminiProvider,
        createOllamaProvider,
      } = await import("@pmt/llm");
      const { createSecretStore } = await import("./secrets.js");
      const secrets = createSecretStore();

      let provider;
      switch (providerId) {
        case "anthropic_api":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(
            `provider_${providerId}_apiKey`,
            credentials.apiKey
          );
          provider = createAnthropicProvider({
            mode: "api_key",
            apiKey: credentials.apiKey,
          });
          break;
        case "deepseek":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(
            `provider_${providerId}_apiKey`,
            credentials.apiKey
          );
          provider = createOpenAICompatProvider({
            providerId: "deepseek" as never,
            displayName: "DeepSeek",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.deepseek.com/v1",
            defaultModels: [
              { id: "deepseek-chat", contextWindow: 128000 },
              { id: "deepseek-reasoner", contextWindow: 128000 },
            ],
          });
          break;
        case "zhipu":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(
            `provider_${providerId}_apiKey`,
            credentials.apiKey
          );
          provider = createOpenAICompatProvider({
            providerId: "zhipu" as never,
            displayName: "Zhipu / Z.ai",
            apiKey: credentials.apiKey,
            baseUrl: "https://open.bigmodel.cn/api/paas/v4",
            defaultModels: [
              { id: "glm-4.5", contextWindow: 128000 },
              { id: "glm-4-flash", contextWindow: 128000 },
            ],
          });
          break;
        case "openai":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(
            `provider_${providerId}_apiKey`,
            credentials.apiKey
          );
          provider = createOpenAICompatProvider({
            providerId: "openai" as never,
            displayName: "OpenAI",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.openai.com/v1",
            defaultModels: [{ id: "gpt-5", contextWindow: 200000 }],
          });
          break;
        case "gemini_api":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(
            `provider_${providerId}_apiKey`,
            credentials.apiKey
          );
          provider = createGeminiProvider({
            mode: "api_key",
            apiKey: credentials.apiKey,
          });
          break;
        case "ollama":
          provider = createOllamaProvider({
            baseUrl: credentials.baseUrl ?? "http://localhost:11434",
          });
          break;
        default:
          throw new Error(`unknown provider: ${providerId}`);
      }

      await provider.connect();
      ctx.registry.register(provider);
    }
  );

  ipcMain.handle("disconnectProvider", async (_e, providerId: string) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.registry.unregister(providerId as never);
  });

  ipcMain.handle(
    "setAgentModel",
    async (_e, agentId: string, providerId: string, modelId: string) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");
      ctx.registry.assignAgentModel(
        agentId as never,
        providerId as never,
        modelId
      );
    }
  );

  // Chat
  ipcMain.handle(
    "getChatHistory",
    async (_e, agentId: string, limit: number) => {
      const ctx = deps.getEngineContext();
      if (!ctx) return [];
      return ctx.db
        .prepare(
          "SELECT * FROM chat_messages WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?"
        )
        .all(agentId, limit);
    }
  );

  ipcMain.handle("sendMessage", async (_e, _agentId: string, _content: string) => {
    // M5.9 will implement streaming chat via riskMgrRunner / runner
    return null;
  });

  ipcMain.handle("clearChatHistory", async (_e, agentId: string) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db.prepare("DELETE FROM chat_messages WHERE agent_id = ?").run(agentId);
  });

  // Engine control
  ipcMain.handle("pauseTrading", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    ctx.collector.stop();
  });

  ipcMain.handle("resumeTrading", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    await ctx.collector.start();
  });

  ipcMain.handle("emergencyStop", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    ctx.collector.stop();
    // M5.10 will also force-close all positions
  });
}
