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
import type { ReviewerScheduler } from "./reviewer-scheduler.js";
import type { CoordinatorScheduler } from "./coordinator.js";
import type { WindowHandle } from "./window.js";
import { getLogDir, readLatestLogs, listLogFiles } from "./logger.js";

export interface IpcDeps {
  getEngineContext: () => EngineContext | null;
  getRiskMgrRunner: () => RiskMgrRunner | null;
  getReviewerScheduler: () => ReviewerScheduler | null;
  getCoordinatorScheduler: () => CoordinatorScheduler | null;
  getMainWindow: () => WindowHandle | null;
}

export function registerIpcHandlers(deps: IpcDeps): void {
  // Portfolio
  ipcMain.handle("getPortfolioState", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    // Use portfolioRepo to get defaults if table is empty
    const state = ctx.portfolioRepo.read();
    return {
      total_capital: state.total_capital,
      current_equity: state.current_equity,
      day_start_equity: state.day_start_equity,
      week_start_equity: state.week_start_equity,
      peak_equity: state.peak_equity,
      current_drawdown: state.current_drawdown,
      daily_halt_triggered: state.daily_halt_triggered,
      weekly_halt_triggered: state.weekly_halt_triggered,
    };
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
    const sched = deps.getCoordinatorScheduler();
    if (!sched) throw new Error("coordinator scheduler not started");
    return sched.triggerNow();
  });

  // Reports
  ipcMain.handle("getRecentReports", async (_e, limit: number) => {
    const { readdirSync, statSync } = await import("node:fs");
    const { join } = await import("node:path");
    const { homedir } = await import("node:os");
    const reportsDir = process.env.POLYMARKET_TRADER_HOME
      ? join(process.env.POLYMARKET_TRADER_HOME, "reports")
      : join(homedir(), ".polymarket-trader", "reports");

    try {
      const files = readdirSync(reportsDir)
        .filter((f) => f.startsWith("review-") && f.endsWith(".md"))
        .map((f) => {
          const fullPath = join(reportsDir, f);
          const stat = statSync(fullPath);
          const dateStr = f.slice("review-".length, -".md".length);
          return {
            path: fullPath,
            date: dateStr,
            mtime: stat.mtimeMs,
          };
        })
        .sort((a, b) => b.mtime - a.mtime)
        .slice(0, limit);
      return files;
    } catch {
      return [];
    }
  });

  ipcMain.handle("getReportContent", async (_e, reportPath: string) => {
    const { readFileSync } = await import("node:fs");
    try {
      return readFileSync(reportPath, "utf-8");
    } catch {
      return "";
    }
  });

  ipcMain.handle("triggerReviewerNow", async () => {
    const sched = deps.getReviewerScheduler();
    if (!sched) throw new Error("reviewer scheduler not started");
    await sched.triggerNow();
    return true;
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
    const proposal = ctx.db
      .prepare("SELECT * FROM filter_proposals WHERE proposal_id = ?")
      .get(id) as
      | { field: string; proposed_value: string; status: string }
      | undefined;
    if (!proposal) throw new Error(`proposal ${id} not found`);
    if (proposal.status !== "pending")
      throw new Error(`proposal ${id} is not pending`);

    // Apply to filter_config in a transaction so the proposal status flip and
    // the config write land atomically.
    ctx.db.transaction(() => {
      ctx.db
        .prepare(
          "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
        )
        .run(proposal.field, proposal.proposed_value, Date.now(), `proposal:${id}`);
      ctx.db
        .prepare(
          "UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?"
        )
        .run(Date.now(), id);
    })();
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
    // Map internal config names to frontend-friendly names
    const cfg = ctx.config;
    return {
      // Thresholds
      minTradeUsdc: cfg.minTradeUsdc,
      minNetFlow1m: cfg.minNetFlow1mUsdc,
      minUniqueTraders1m: cfg.minUniqueTraders1m,
      minPriceMove5m: cfg.minPriceMove5m,
      minLiquidity: cfg.minLiquidityUsdc,
      deadZoneMin: cfg.staticDeadZone[0],
      deadZoneMax: cfg.staticDeadZone[1],
      // Risk limits
      totalCapital: cfg.maxTotalPositionUsdc,
      maxPositionUsdc: cfg.maxPositionUsdc,
      maxSingleLoss: cfg.maxSingleTradeLossUsdc,
      maxOpenPositions: cfg.maxOpenPositions,
      dailyHaltPct: cfg.dailyLossHaltPct,
      takeProfitPct: cfg.takeProfitPct,
      stopLossPct: cfg.stopLossPctNormal,
    };
  });

  ipcMain.handle(
    "updateConfigField",
    async (_e, key: string, value: unknown) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");

      // Map frontend field names to internal config field names
      const fieldMapping: Record<string, string> = {
        minTradeUsdc: "minTradeUsdc",
        minNetFlow1m: "minNetFlow1mUsdc",
        minUniqueTraders1m: "minUniqueTraders1m",
        minPriceMove5m: "minPriceMove5m",
        minLiquidity: "minLiquidityUsdc",
        deadZoneMin: "staticDeadZoneMin",
        deadZoneMax: "staticDeadZoneMax",
        totalCapital: "maxTotalPositionUsdc",
        maxPositionUsdc: "maxPositionUsdc",
        maxSingleLoss: "maxSingleTradeLossUsdc",
        maxOpenPositions: "maxOpenPositions",
        dailyHaltPct: "dailyLossHaltPct",
        takeProfitPct: "takeProfitPct",
        stopLossPct: "stopLossPctNormal",
      };

      const internalKey = fieldMapping[key] || key;

      try {
        ctx.db
          .prepare(
            "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
          )
          .run(internalKey, JSON.stringify(value), Date.now(), "user");

        // Also update the in-memory config if the field exists
        if (ctx.config && internalKey in ctx.config) {
          (ctx.config as unknown as Record<string, unknown>)[internalKey] = value;
        }
        return { success: true };
      } catch (err) {
        console.error("[ipc] updateConfigField failed:", err);
        throw err;
      }
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
      console.log("[ipc] connectProvider called:", providerId);
      const ctx = deps.getEngineContext();
      if (!ctx) {
        console.error("[ipc] connectProvider failed: engine not running");
        throw new Error("engine not running");
      }

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
      console.log("[ipc] Creating provider for:", providerId);
      switch (providerId) {
        case "anthropic_api":
          console.log("[ipc] Creating Anthropic provider");
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
        case "moonshot":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
          provider = createOpenAICompatProvider({
            providerId: "moonshot" as never,
            displayName: "Moonshot",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.moonshot.cn/v1",
            defaultModels: [
              { id: "moonshot-v1-8k", contextWindow: 8192 },
              { id: "moonshot-v1-32k", contextWindow: 32768 },
              { id: "moonshot-v1-128k", contextWindow: 128000 },
            ],
          });
          break;
        case "qwen":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
          provider = createOpenAICompatProvider({
            providerId: "qwen" as never,
            displayName: "Qwen",
            apiKey: credentials.apiKey,
            baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            defaultModels: [
              { id: "qwen-max", contextWindow: 128000 },
              { id: "qwen-plus", contextWindow: 128000 },
              { id: "qwen-turbo", contextWindow: 128000 },
            ],
          });
          break;
        case "groq":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
          provider = createOpenAICompatProvider({
            providerId: "groq" as never,
            displayName: "Groq",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.groq.com/openai/v1",
            defaultModels: [
              { id: "llama-3.3-70b-versatile", contextWindow: 128000 },
              { id: "llama-3.1-8b-instant", contextWindow: 128000 },
              { id: "mixtral-8x7b-32768", contextWindow: 32768 },
            ],
          });
          break;
        case "mistral":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
          provider = createOpenAICompatProvider({
            providerId: "mistral" as never,
            displayName: "Mistral",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.mistral.ai/v1",
            defaultModels: [
              { id: "mistral-large-latest", contextWindow: 128000 },
              { id: "mistral-medium-latest", contextWindow: 128000 },
              { id: "mistral-small-latest", contextWindow: 128000 },
            ],
          });
          break;
        case "xai":
          if (!credentials.apiKey) throw new Error("API key required");
          await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
          provider = createOpenAICompatProvider({
            providerId: "xai" as never,
            displayName: "xAI",
            apiKey: credentials.apiKey,
            baseUrl: "https://api.x.ai/v1",
            defaultModels: [
              { id: "grok-2", contextWindow: 128000 },
              { id: "grok-2-vision", contextWindow: 128000 },
            ],
          });
          break;
        // Subscription / OAuth providers
        case "anthropic_subscription":
          provider = createAnthropicProvider({
            mode: "subscription",
            readCliToken: async () => {
              // Try to read from environment or prompt user
              const token = process.env.ANTHROPIC_CLI_TOKEN;
              if (!token) throw new Error("ANTHROPIC_CLI_TOKEN environment variable not set");
              return token;
            },
          });
          break;
        case "gemini_oauth":
          provider = createGeminiProvider({
            mode: "oauth",
            getAccessToken: async () => {
              const token = process.env.GEMINI_ACCESS_TOKEN;
              if (!token) throw new Error("GEMINI_ACCESS_TOKEN environment variable not set");
              return token;
            },
          });
          break;
        // Coding plan providers - use OpenAI compatible with OAuth token
        case "zhipu_coding":
          provider = createOpenAICompatProvider({
            providerId: "zhipu_coding" as never,
            displayName: "Zhipu (Coding Plan)",
            apiKey: process.env.ZHIPU_CODING_TOKEN || "",
            baseUrl: "https://open.bigmodel.cn/api/paas/v4",
            defaultModels: [
              { id: "glm-4.5", contextWindow: 128000 },
              { id: "glm-4-flash", contextWindow: 128000 },
            ],
          });
          break;
        case "qwen_coding":
          provider = createOpenAICompatProvider({
            providerId: "qwen_coding" as never,
            displayName: "Qwen (Coding Plan)",
            apiKey: process.env.QWEN_CODING_TOKEN || "",
            baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            defaultModels: [
              { id: "qwen-max", contextWindow: 128000 },
              { id: "qwen-plus", contextWindow: 128000 },
            ],
          });
          break;
        case "kimi_code":
          provider = createOpenAICompatProvider({
            providerId: "kimi_code" as never,
            displayName: "Kimi (Code Plan)",
            apiKey: process.env.KIMI_CODE_TOKEN || "",
            baseUrl: "https://api.moonshot.cn/v1",
            defaultModels: [
              { id: "kimi-k1-5", contextWindow: 128000 },
              { id: "kimi-k1-5-32k", contextWindow: 32768 },
            ],
          });
          break;
        case "minimax_coding":
          provider = createOpenAICompatProvider({
            providerId: "minimax_coding" as never,
            displayName: "MiniMax (Coding Plan)",
            apiKey: process.env.MINIMAX_CODING_TOKEN || "",
            baseUrl: "https://api.minimax.chat/v1",
            defaultModels: [
              { id: "MiniMax-M2.1", contextWindow: 128000 },
              { id: "MiniMax-Text-01", contextWindow: 1000000 },
            ],
          });
          break;
        case "volcengine_coding":
          provider = createOpenAICompatProvider({
            providerId: "volcengine_coding" as never,
            displayName: "Volcengine (Coding Plan)",
            apiKey: process.env.VOLCENGINE_CODING_TOKEN || "",
            baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
            defaultModels: [
              { id: "doubao-pro-32k", contextWindow: 32000 },
              { id: "doubao-pro-128k", contextWindow: 128000 },
              { id: "doubao-lite-32k", contextWindow: 32000 },
            ],
          });
          break;
        default:
          throw new Error(`unknown provider: ${providerId}`);
      }

      console.log("[ipc] Connecting to provider...");
      await provider.connect();
      console.log("[ipc] Provider connected, registering...");
      ctx.registry.register(provider);
      console.log("[ipc] Provider registered successfully");
      return { success: true, providerId };
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

  // M5.9b: Streaming chat IPC - sends token-by-token updates to renderer
  ipcMain.handle(
    "sendMessageStream",
    async (_e, agentId: string, content: string) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");
      const window = deps.getMainWindow();
      const wc = window?.webContents();

      // Persist user message
      ctx.db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run(agentId, "user", content, Date.now());

      // Notify renderer that user message was added
      wc?.send("chat:message", { agentId, role: "user", content });

      if (agentId !== "risk_manager") {
        // M5: only risk_manager has reactive chat. Analyzer/Reviewer chats
        // can be added in a follow-up task.
        const placeholder = `(${agentId} chat not yet wired — coming in a follow-up task)`;
        ctx.db
          .prepare(
            "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
          )
          .run(agentId, "assistant", placeholder, Date.now());
        wc?.send("chat:complete", { agentId, role: "assistant", content: placeholder });
        return { content: placeholder };
      }

      const runner = deps.getRiskMgrRunner();
      if (!runner) throw new Error("risk manager runner not configured");

      // Build current system state snapshot
      const portfolioRows = ctx.db
        .prepare("SELECT key, value FROM portfolio_state")
        .all() as Array<{ key: string; value: string }>;
      const portfolioState = Object.fromEntries(
        portfolioRows.map((r) => {
          try {
            return [r.key, JSON.parse(r.value)];
          } catch {
            return [r.key, r.value];
          }
        })
      ) as Record<string, unknown>;
      const recentTrades = ctx.db
        .prepare(
          "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
        )
        .all() as Array<{
        market_title: string;
        direction: string;
        pnl_net_usdc: number | null;
        exit_reason: string | null;
      }>;
      const openCountRow = ctx.db
        .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
        .get() as { n: number } | undefined;
      const openCount = openCountRow?.n ?? 0;

      // Start streaming - first notify renderer that assistant is starting to respond
      wc?.send("chat:streaming:start", { agentId });

      let fullContent = "";
      const assigned = ctx.registry.getProviderForAgent("risk_manager");
      
      if (assigned) {
        try {
          const stream = assigned.provider.streamChat({
            model: assigned.modelId,
            messages: [
              { role: "system", content: "You are the Polymarket Risk Manager / Coordinator. Answer user questions concisely and cite specific numbers." },
              { role: "user", content: `System state:\ncurrent_equity: $${Number(portfolioState.current_equity ?? 10000).toFixed(2)}\nday_start_equity: $${Number(portfolioState.day_start_equity ?? 10000).toFixed(2)}\ndaily_halt_triggered: ${portfolioState.daily_halt_triggered ?? false}\nopen_position_count: ${openCount}\n\nQuestion: ${content}` },
            ],
            temperature: 0.3,
            maxTokens: 500,
          });

          for await (const chunk of stream) {
            if (chunk.delta) {
              fullContent += chunk.delta;
              wc?.send("chat:streaming:delta", { agentId, delta: chunk.delta });
            }
            if (chunk.done && chunk.final) {
              fullContent = chunk.final.content;
            }
          }
        } catch (err) {
          fullContent = `(Error: ${String(err).slice(0, 100)})`;
        }
      } else {
        // Fallback to non-streaming if provider doesn't support streaming
        fullContent = await runner.answerQuestion({
          question: content,
          systemState: {
            portfolioState: {
              current_equity: Number(portfolioState.current_equity ?? 10000),
              day_start_equity: Number(portfolioState.day_start_equity ?? 10000),
              daily_halt_triggered: Boolean(
                portfolioState.daily_halt_triggered ?? false
              ),
            },
            recentTrades,
            openPositionCount: openCount,
          },
        });
      }

      // Persist assistant message
      ctx.db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run(agentId, "assistant", fullContent, Date.now());

      // Notify renderer that streaming is complete
      wc?.send("chat:streaming:complete", { agentId, content: fullContent });

      return { content: fullContent };
    }
  );

  // Legacy non-streaming handler (kept for backward compatibility)
  ipcMain.handle(
    "sendMessage",
    async (_e, agentId: string, content: string) => {
      const ctx = deps.getEngineContext();
      if (!ctx) throw new Error("engine not running");
      const window = deps.getMainWindow();

      // Persist user message
      ctx.db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run(agentId, "user", content, Date.now());

      if (agentId !== "risk_manager") {
        // M5: only risk_manager has reactive chat. Analyzer/Reviewer chats
        // can be added in a follow-up task.
        const placeholder = `(${agentId} chat not yet wired — coming in a follow-up task)`;
        ctx.db
          .prepare(
            "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
          )
          .run(agentId, "assistant", placeholder, Date.now());
        return { content: placeholder };
      }

      const runner = deps.getRiskMgrRunner();
      if (!runner) throw new Error("risk manager runner not configured");

      // Build current system state snapshot
      const portfolioRows = ctx.db
        .prepare("SELECT key, value FROM portfolio_state")
        .all() as Array<{ key: string; value: string }>;
      const portfolioState = Object.fromEntries(
        portfolioRows.map((r) => {
          try {
            return [r.key, JSON.parse(r.value)];
          } catch {
            return [r.key, r.value];
          }
        })
      ) as Record<string, unknown>;
      const recentTrades = ctx.db
        .prepare(
          "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
        )
        .all() as Array<{
        market_title: string;
        direction: string;
        pnl_net_usdc: number | null;
        exit_reason: string | null;
      }>;
      const openCountRow = ctx.db
        .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
        .get() as { n: number } | undefined;
      const openCount = openCountRow?.n ?? 0;

      const reply: string = await runner.answerQuestion({
        question: content,
        systemState: {
          portfolioState: {
            current_equity: Number(portfolioState.current_equity ?? 10000),
            day_start_equity: Number(portfolioState.day_start_equity ?? 10000),
            daily_halt_triggered: Boolean(
              portfolioState.daily_halt_triggered ?? false
            ),
          },
          recentTrades,
          openPositionCount: openCount,
        },
      });

      // Persist assistant message
      ctx.db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run(agentId, "assistant", reply, Date.now());

      // Notify renderer (event push)
      const wc = window?.webContents();
      wc?.send("chat:complete", { agentId, role: "assistant", content: reply });

      return { content: reply };
    }
  );

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

  // Rollback auto-applied filter config changes
  ipcMain.handle("rollbackAutoApply", async (_e, historyId: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");

    const historyRow = ctx.db
      .prepare("SELECT * FROM filter_config_history WHERE history_id = ?")
      .get(historyId) as
      | { history_id: number; key: string; old_value: string; new_value: string; proposal_id: number | null; rolled_back_at: number | null }
      | undefined;

    if (!historyRow) throw new Error(`history entry ${historyId} not found`);
    if (historyRow.rolled_back_at) throw new Error(`history entry ${historyId} already rolled back`);

    ctx.db.transaction(() => {
      // Restore old value to filter_config
      ctx.db
        .prepare(
          "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
        )
        .run(historyRow.key, historyRow.old_value, Date.now(), `rollback:${historyId}`);

      // Mark history entry as rolled back
      ctx.db
        .prepare("UPDATE filter_config_history SET rolled_back_at = ?, rollback_reason = ? WHERE history_id = ?")
        .run(Date.now(), "user_rollback", historyId);

      // Also revert the proposal status back to pending so it can be re-reviewed
      if (historyRow.proposal_id) {
        ctx.db
          .prepare("UPDATE filter_proposals SET status = 'pending', reviewed_at = NULL WHERE proposal_id = ?")
          .run(historyRow.proposal_id);
      }
    })();

    return { success: true };
  });

  // Get auto-apply history for rollback UI
  ipcMain.handle("getAutoApplyHistory", async (_e, limit: number = 50) => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare(
        "SELECT * FROM filter_config_history WHERE source LIKE 'auto-apply:%' ORDER BY changed_at DESC LIMIT ?"
      )
      .all(limit);
  });

  // Proxy configuration
  ipcMain.handle("getProxyConfig", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return { enabled: false, httpProxy: "", httpsProxy: "" };
    const row = ctx.db
      .prepare("SELECT value FROM filter_config WHERE key = 'proxy_config'")
      .get() as { value: string } | undefined;
    if (!row) return { enabled: false, httpProxy: "", httpsProxy: "" };
    try {
      return JSON.parse(row.value);
    } catch {
      return { enabled: false, httpProxy: "", httpsProxy: "" };
    }
  });

  ipcMain.handle("setProxyConfig", async (_e, config: { enabled: boolean; httpProxy: string; httpsProxy: string }) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db
      .prepare(
        "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
      )
      .run("proxy_config", JSON.stringify(config), Date.now(), "user");
    
    // Update environment variables for current process
    if (config.enabled && config.httpsProxy) {
      process.env.https_proxy = config.httpsProxy;
      process.env.HTTPS_PROXY = config.httpsProxy;
    } else {
      delete process.env.https_proxy;
      delete process.env.HTTPS_PROXY;
    }
    if (config.enabled && config.httpProxy) {
      process.env.http_proxy = config.httpProxy;
      process.env.HTTP_PROXY = config.httpProxy;
    } else {
      delete process.env.http_proxy;
      delete process.env.HTTP_PROXY;
    }
    
    return { success: true };
  });

  // Logging
  ipcMain.handle("getLogDir", async () => {
    return getLogDir();
  });

  ipcMain.handle("getLatestLogs", async (_e, maxLines: number = 500) => {
    return readLatestLogs(maxLines);
  });

  ipcMain.handle("listLogFiles", async () => {
    return listLogFiles();
  });

  ipcMain.handle("openLogDir", async () => {
    const { shell } = await import("electron");
    const logDir = getLogDir();
    await shell.openPath(logDir);
    return { success: true };
  });
}
