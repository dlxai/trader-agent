/**
 * Engine boot/shutdown lifecycle for the Electron main process.
 *
 * Wires together the @pmt/engine pieces (db, bus, collector, executor) and
 * the @pmt/llm provider registry into a single EngineContext that the rest
 * of the main process (IPC handlers, coordinator) can consume.
 *
 * This module is intentionally tolerant of running outside Electron: when
 * `app.getPath("userData")` is unavailable (e.g. in unit tests) it falls back
 * to the `POLYMARKET_TRADER_HOME` env var, then `~/.polymarket-trader`.
 */
import { app } from "electron";
import { join } from "node:path";
import { homedir } from "node:os";
import {
  openDatabase,
  createEventBus,
  createCollector,
  createExecutor,
  createPaperFiller,
  createSignalLogRepo,
  createPortfolioStateRepo,
  loadConfig,
  createPolymarketWsClient,
  createClobWsClient,
  createPolymarketMarketMetadataProvider,
  setAnalyzerCallback,
  getAnalyzerCallback,
  getEventBusForExternal,
  packContext,
  parseVerdict,
  type EventBus,
  type Collector,
  type Executor,
  type TraderConfig,
  type MarketMetadata,
  type TriggerEvent,
  type VerdictEvent,
} from "@pmt/engine";
import { createProviderRegistry, createPositionEvaluatorRunner, type ProviderRegistry } from "@pmt/llm";
import { createPositionEvaluatorLoop, createLiveFiller, type OrderFiller } from "@pmt/engine";
import { createClobOrderService } from "./clob-client.js";
import { getLogger } from "./logger.js";

// Derive the better-sqlite3 Database type from the engine factory so that
// @pmt/main does not need a direct dependency on better-sqlite3.
type EngineDatabase = ReturnType<typeof openDatabase>;

export interface EngineContext {
  db: EngineDatabase;
  dbPath: string;
  config: TraderConfig;
  bus: EventBus;
  collector: Collector;
  executor: Executor;
  registry: ProviderRegistry;
  portfolioRepo: ReturnType<typeof createPortfolioStateRepo>;
}

let activeContext: EngineContext | null = null;

const noopLogger = {
  info: (_m: string): void => {},
  warn: (_m: string): void => {},
  error: (_m: string): void => {},
};

// Helper to get logger safely (may not be initialized during early boot)
function getLoggerSafe() {
  try {
    return getLogger();
  } catch {
    return console;
  }
}

/**
 * Resolve the on-disk data directory for the trader.
 *
 * Order of precedence:
 *   1. POLYMARKET_TRADER_HOME env var (used by tests + power users)
 *   2. Electron app.getPath("userData") (production)
 *   3. ~/.polymarket-trader (fallback if Electron unavailable)
 */
function resolveDataDir(): string {
  const envHome = process.env.POLYMARKET_TRADER_HOME;
  if (envHome && envHome.trim().length > 0) {
    return envHome;
  }
  try {
    return app.getPath("userData");
  } catch {
    return join(homedir(), ".polymarket-trader");
  }
}

/**
 * Create a real market-metadata provider using Polymarket Gamma API.
 * Falls back to placeholder if API call fails.
 */
function createRealMarketMetadataProvider(proxyUrl?: string) {
  return createPolymarketMarketMetadataProvider(proxyUrl ? { proxyUrl } : undefined);
}

/**
 * Boot the engine. Idempotent: returns the existing context if already booted.
 */
export async function bootEngine(): Promise<EngineContext> {
  if (activeContext) return activeContext;

  const dataDir = resolveDataDir();
  const dbPath = join(dataDir, "data.db");
  const db = openDatabase(dbPath);

  // Load base config then apply database overrides
  let config = loadConfig(undefined);
  config = applyDatabaseConfigOverrides(db, config);
  const signalRepo = createSignalLogRepo(db);
  const portfolioRepo = createPortfolioStateRepo(db);
  const bus = createEventBus();
  const registry = createProviderRegistry();

  const logger = getLoggerSafe();

  try {
    await loadStoredProviders(registry);
  } catch (err) {
    logger.error("[lifecycle] failed to load stored providers: %s", err);
  }

  // Load proxy configuration from database or environment
  let proxyUrl: string | undefined = process.env.https_proxy || process.env.HTTPS_PROXY;
  if (proxyUrl) {
    logger.info(`[lifecycle] Using proxy from environment: ${proxyUrl}`);
  }

  // Also check database for proxy config (can override env)
  try {
    const proxyRow = db.prepare("SELECT value FROM filter_config WHERE key = 'proxy_config'").get() as { value: string } | undefined;
    if (proxyRow) {
      const proxyConfig = JSON.parse(proxyRow.value) as { enabled: boolean; httpsProxy: string };
      if (proxyConfig.enabled && proxyConfig.httpsProxy) {
        proxyUrl = proxyConfig.httpsProxy;
        logger.info(`[lifecycle] Using proxy from database: ${proxyUrl}`);
      }
    }
  } catch {
    // Ignore proxy config errors
  }

  // Use default proxy if none configured
  if (!proxyUrl) {
    const defaultProxy = "http://127.0.0.1:7890";
    proxyUrl = defaultProxy;
    logger.info(`[lifecycle] Using default proxy: ${proxyUrl}`);

    // Save default config to database for UI consistency
    try {
      const defaultConfig = { enabled: true, httpProxy: defaultProxy, httpsProxy: defaultProxy };
      db.prepare(
        "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
      ).run("proxy_config", JSON.stringify(defaultConfig), Date.now(), "default");
      logger.info(`[lifecycle] Default proxy config saved to database`);
    } catch (err) {
      logger.error(`[lifecycle] Failed to save default proxy config: %s`, err);
    }
  }

  // Set proxy URL in config for collector HTTP fallback
  config.proxyUrl = proxyUrl;

  // Select filler: live CLOB or paper simulation
  let filler: OrderFiller;
  if (config.liveTrade.mode === "live") {
    try {
      // Read wallet credentials: env vars take priority, then secrets store
      const privateKey = process.env.POLYMARKET_PRIVATE_KEY;
      const funderAddress = process.env.POLYMARKET_FUNDER_ADDRESS;

      let secretPk: string | undefined;
      let secretFunder: string | undefined;
      if (!privateKey || !funderAddress) {
        const { createSecretStore } = await import("./secrets.js");
        const secrets = createSecretStore();
        if (!privateKey) secretPk = (await secrets.get("live_trade_privateKey")) ?? undefined;
        if (!funderAddress) secretFunder = (await secrets.get("live_trade_funderAddress")) ?? undefined;
      }

      const pk = privateKey ?? secretPk;
      const funder = funderAddress ?? secretFunder;

      if (pk && funder) {
        const clobService = createClobOrderService({
          privateKey: pk,
          funderAddress: funder,
          chainId: 137,
        });
        await clobService.initialize();
        filler = createLiveFiller({
          clob: clobService,
          slippageThreshold: config.liveTrade.slippageThreshold,
          maxSlippage: config.liveTrade.maxSlippage,
          limitOrderTimeoutSec: config.liveTrade.limitOrderTimeoutSec,
        });
        logger.info("[lifecycle] Live trading mode enabled");
      } else {
        logger.warn("[lifecycle] Live mode configured but credentials missing, falling back to paper");
        filler = createPaperFiller({ slippagePct: config.paperSlippagePct });
      }
    } catch (err) {
      logger.error(`[lifecycle] Failed to initialize live trading: ${err}`);
      filler = createPaperFiller({ slippagePct: config.paperSlippagePct });
    }
  } else {
    filler = createPaperFiller({ slippagePct: config.paperSlippagePct });
  }

  const executor = createExecutor({
    config,
    bus,
    signalRepo,
    portfolioRepo,
    filler,
    logger: noopLogger,
  });

  // Position evaluator loop
  if (config.aiExit.enabled) {
    const peRunner = createPositionEvaluatorRunner({ registry });
    const positionEvaluatorLoop = createPositionEvaluatorLoop({
      intervalSec: config.aiExit.intervalSec,
      getOpenPositions: () => executor.openPositions(),
      evaluate: (account, positions) => peRunner.evaluate(account, positions),
      onAction: (action) => {
        if (action.action === "close") {
          const pos = executor.openPositions().find((p) => p.signal_id === action.signal_id);
          if (pos) {
            const lastPrice = executor.getLastPrice(pos.market_id) ?? pos.entry_price;
            void executor.closePosition(pos, lastPrice, Date.now(), "AI_EXIT");
          }
        }
      },
    });
    positionEvaluatorLoop.start();
  }

  logger.info(`[lifecycle] Creating collector with proxyUrl: ${proxyUrl || 'none'}`);

  const collector = createCollector({
    config,
    bus,
    executor,
    wsClientFactory: (onTrade) =>
      createPolymarketWsClient({
        // Use Activity WebSocket (RTDS) for trade activity stream
        url: config.polymarketActivityWsUrl,
        onTrade,
        onError: (err) => logger.error(`[ws-activity] ${err.message}`),
        ...(proxyUrl ? { proxyUrl } : {}),
      }),
    // Temporarily disable CLOB WebSocket due to connection issues
    // clobWsClientFactory: (onPriceUpdate) =>
    //   createClobWsClient({
    //     url: config.polymarketClobWsUrl,
    //     onPriceUpdate,
    //     onError: (err) => logger.error(`[ws-clob] ${err.message}`),
    //     ...(proxyUrl ? { proxyUrl } : {}),
    //   }),
    marketMetadataProvider: createRealMarketMetadataProvider(proxyUrl),
    logger: {
      info: (msg: string) => logger.info(`[collector] ${msg}`),
      warn: (msg: string) => logger.warn(`[collector] ${msg}`),
      error: (msg: string) => logger.error(`[collector] ${msg}`),
    },
  });

  // Set up Analyzer LLM integration
  setAnalyzerCallback(async (trigger: TriggerEvent): Promise<VerdictEvent | null> => {
    const assigned = registry.getProviderForAgent("analyzer");
    if (!assigned) {
      logger.warn("[lifecycle] No LLM provider available for analyzer");
      return null;
    }

    try {
      const prompt = packContext(trigger);
      const systemPrompt = getAnalyzerSystemPrompt(config.prompt?.customPrompt);
      const response = await assigned.provider.chat({
        model: assigned.modelId,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: prompt },
        ],
        temperature: 0.3,
        maxTokens: 500,
      });

      if (!response) return null;

      const parsed = parseVerdict(response.content);

      // Downgrade to "uncertain" if confidence falls below the configured threshold
      const minConfidence = config.prompt?.minConfidence ?? 0.65;
      if (parsed.confidence < minConfidence) {
        logger.info(
          `[lifecycle] Confidence ${parsed.confidence} below threshold ${minConfidence}, downgrading verdict to uncertain`
        );
        parsed.verdict = "uncertain";
      }

      const verdictEvent: VerdictEvent = {
        type: "verdict",
        trigger,
        verdict: parsed.verdict,
        confidence: parsed.confidence,
        reasoning: parsed.reasoning,
        llm_direction: parsed.direction,
      };

      return verdictEvent;
    } catch (err) {
      logger.error("[lifecycle] Analyzer LLM error: %s", err);
      return null;
    }
  });

  // Connect EventBus flow: Trigger -> Analyzer -> Verdict -> Executor
  // Step 1: Subscribe to Triggers, send to Analyzer
  bus.onTrigger(async (trigger) => {
    const analyzerCb = getAnalyzerCallback();
    if (!analyzerCb) {
      logger.warn("[lifecycle] No analyzer callback registered");
      return;
    }
    try {
      const verdict = await analyzerCb(trigger);
      if (verdict) {
        bus.publishVerdict(verdict);
        logger.info(`[lifecycle] Analyzer verdict: ${verdict.verdict} for ${trigger.market_id}`);
      }
    } catch (err) {
      logger.error("[lifecycle] Analyzer error: %s", err);
    }
  });

  // Step 2: Subscribe to Verdicts, send to Executor
  bus.onVerdict((verdict) => {
    void executor.handleVerdict(verdict);
  });

  activeContext = {
    db,
    dbPath,
    config,
    bus,
    collector,
    executor,
    registry,
    portfolioRepo,
  };
  return activeContext;
}

function getAnalyzerSystemPrompt(customPrompt?: string): string {
  const base = `You are the Polymarket Analyzer. Your job is to assess trading signals.

Look for red flags (lean toward noise):
- Unique traders < 3 with no large order exemption -> likely bots
- Price move < 3% over 5m -> insufficient conviction  
- Liquidity < $5000 -> slippage will eat profit
- Market title contains gambling templates

Look for green flags (lean toward real_signal):
- Net flow > $5000 with 5+ unique traders -> broad participation
- Price move aligned with net flow direction -> coherent move
- Resolving in hours, not weeks -> event-driven window
- Price in middle range (0.25-0.60) -> asymmetric payoff

Hard constraints:
- NEVER suggest trading in dead zone [0.60, 0.85]
- Confidence is for audit only, not a gate
- Respond with JSON only

Output format:
{
  "verdict": "real_signal" | "noise" | "uncertain",
  "direction": "buy_yes" | "buy_no",
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation"
}`;
  return customPrompt && customPrompt.trim().length > 0
    ? `${base}\n\n${customPrompt.trim()}`
    : base;
}

/**
 * Shutdown the engine. Idempotent: safe to call when not booted.
 *
 * Stops the collector (closes WS) and closes the SQLite handle. Errors from
 * either step are swallowed so a partial-boot failure can still be unwound.
 */
export async function shutdownEngine(): Promise<void> {
  if (!activeContext) return;
  try {
    activeContext.collector.stop();
  } catch {
    // ignore — collector may not have started
  }
  try {
    activeContext.db.close();
  } catch {
    // ignore — db may already be closed
  }
  activeContext = null;
}

/** Returns the active engine context, or null if not booted. */
export function getEngineContext(): EngineContext | null {
  return activeContext;
}

/**
 * Apply configuration overrides from the database filter_config table.
 * This allows runtime configuration changes via the desktop UI.
 */
function applyDatabaseConfigOverrides(db: EngineDatabase, config: TraderConfig): TraderConfig {
  const logger = getLoggerSafe();
  try {
    const rows = db.prepare("SELECT key, value FROM filter_config").all() as Array<{ key: string; value: string }>;
    const overrides: Record<string, unknown> = {};

    for (const row of rows) {
      try {
        overrides[row.key] = JSON.parse(row.value);
      } catch {
        overrides[row.key] = row.value;
      }
    }

    // Map database keys to config fields
    if (overrides.minTradeUsdc !== undefined) config.minTradeUsdc = Number(overrides.minTradeUsdc);
    if (overrides.minNetFlow1mUsdc !== undefined) config.minNetFlow1mUsdc = Number(overrides.minNetFlow1mUsdc);
    if (overrides.minUniqueTraders1m !== undefined) config.minUniqueTraders1m = Number(overrides.minUniqueTraders1m);
    if (overrides.minPriceMove5m !== undefined) config.minPriceMove5m = Number(overrides.minPriceMove5m);
    if (overrides.minLiquidityUsdc !== undefined) config.minLiquidityUsdc = Number(overrides.minLiquidityUsdc);
    if (overrides.staticDeadZoneMin !== undefined && overrides.staticDeadZoneMax !== undefined) {
      config.staticDeadZone = [Number(overrides.staticDeadZoneMin), Number(overrides.staticDeadZoneMax)];
    }
    if (overrides.maxTotalPositionUsdc !== undefined) config.maxTotalPositionUsdc = Number(overrides.maxTotalPositionUsdc);
    if (overrides.maxPositionUsdc !== undefined) config.maxPositionUsdc = Number(overrides.maxPositionUsdc);
    if (overrides.maxSingleTradeLossUsdc !== undefined) config.maxSingleTradeLossUsdc = Number(overrides.maxSingleTradeLossUsdc);
    if (overrides.maxOpenPositions !== undefined) config.maxOpenPositions = Number(overrides.maxOpenPositions);
    if (overrides.dailyLossHaltPct !== undefined) config.dailyLossHaltPct = Number(overrides.dailyLossHaltPct);
    if (overrides.takeProfitPct !== undefined) config.takeProfitPct = Number(overrides.takeProfitPct);
    if (overrides.stopLossPctNormal !== undefined) config.stopLossPctNormal = Number(overrides.stopLossPctNormal);

    logger.info("[lifecycle] Applied %d config overrides from database", rows.length);
  } catch (err) {
    logger.error("[lifecycle] Failed to load config overrides from database: %s", err);
  }
  return config;
}

/**
 * Reconnect any LLM providers whose API keys are already stored in the
 * secrets store. Each provider is wrapped in its own try/catch so that a
 * single bad credential never blocks the rest of the app from booting.
 */
async function loadStoredProviders(registry: ProviderRegistry): Promise<void> {
  const logger = getLoggerSafe();
  const { createSecretStore } = await import("./secrets.js");
  const {
    createAnthropicProvider,
    createOpenAICompatProvider,
    createGeminiProvider,
  } = await import("@pmt/llm");

  const secrets = createSecretStore();
  const keys = await secrets.listKeys();

  for (const key of keys) {
    if (!key.startsWith("provider_") || !key.endsWith("_apiKey")) continue;
    const providerId = key.slice("provider_".length, -"_apiKey".length);
    const apiKey = await secrets.get(key);
    if (!apiKey) continue;

    try {
      let provider;
      switch (providerId) {
        case "anthropic_api":
          provider = createAnthropicProvider({ mode: "api_key", apiKey });
          break;
        case "deepseek":
          provider = createOpenAICompatProvider({
            providerId: "deepseek" as never,
            displayName: "DeepSeek",
            apiKey,
            baseUrl: "https://api.deepseek.com/v1",
            defaultModels: [{ id: "deepseek-chat", contextWindow: 128000 }],
          });
          break;
        case "zhipu":
          provider = createOpenAICompatProvider({
            providerId: "zhipu" as never,
            displayName: "Zhipu",
            apiKey,
            baseUrl: "https://open.bigmodel.cn/api/paas/v4",
            defaultModels: [{ id: "glm-4.5", contextWindow: 128000 }],
          });
          break;
        case "openai":
          provider = createOpenAICompatProvider({
            providerId: "openai" as never,
            displayName: "OpenAI",
            apiKey,
            baseUrl: "https://api.openai.com/v1",
            defaultModels: [{ id: "gpt-5", contextWindow: 200000 }],
          });
          break;
        case "gemini_api":
          provider = createGeminiProvider({ mode: "api_key", apiKey });
          break;
        case "moonshot":
          provider = createOpenAICompatProvider({
            providerId: "moonshot" as never,
            displayName: "Moonshot",
            apiKey,
            baseUrl: "https://api.moonshot.cn/v1",
            defaultModels: [{ id: "moonshot-v1-8k", contextWindow: 8192 }],
          });
          break;
        case "qwen":
          provider = createOpenAICompatProvider({
            providerId: "qwen" as never,
            displayName: "Qwen",
            apiKey,
            baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            defaultModels: [{ id: "qwen-max", contextWindow: 128000 }],
          });
          break;
        case "groq":
          provider = createOpenAICompatProvider({
            providerId: "groq" as never,
            displayName: "Groq",
            apiKey,
            baseUrl: "https://api.groq.com/openai/v1",
            defaultModels: [{ id: "llama-3.3-70b-versatile", contextWindow: 128000 }],
          });
          break;
        case "mistral":
          provider = createOpenAICompatProvider({
            providerId: "mistral" as never,
            displayName: "Mistral",
            apiKey,
            baseUrl: "https://api.mistral.ai/v1",
            defaultModels: [{ id: "mistral-large-latest", contextWindow: 128000 }],
          });
          break;
        case "xai":
          provider = createOpenAICompatProvider({
            providerId: "xai" as never,
            displayName: "xAI",
            apiKey,
            baseUrl: "https://api.x.ai/v1",
            defaultModels: [{ id: "grok-2", contextWindow: 128000 }],
          });
          break;
        // Coding plan providers
        case "zhipu_coding":
          provider = createOpenAICompatProvider({
            providerId: "zhipu_coding" as never,
            displayName: "Zhipu (Coding Plan)",
            apiKey,
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
            apiKey,
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
            apiKey,
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
            apiKey,
            baseUrl: "https://api.minimax.chat/v1",
            defaultModels: [
              { id: "MiniMax-M2.1", contextWindow: 128000 },
              { id: "MiniMax-Text-01", contextWindow: 1000000 },
            ],
          });
          break;
        case "volcengine_coding":
          provider = createAnthropicProvider({
            mode: "api_key",
            apiKey,
            baseUrl: "https://ark.cn-beijing.volces.com/api/coding",
            overrideId: "volcengine_coding",
            displayName: "Volcengine (Coding Plan)",
            models: [
              { id: "doubao-pro-32k", contextWindow: 32000 },
              { id: "doubao-pro-128k", contextWindow: 128000 },
              { id: "doubao-lite-32k", contextWindow: 32000 },
            ],
          });
          break;
      }
      if (provider) {
        await provider.connect();
        registry.register(provider);
      }
    } catch (err) {
      logger.error(`[lifecycle] failed to reconnect %s: %s`, providerId, err);
    }
  }
}
