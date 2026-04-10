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
import { createProviderRegistry, type ProviderRegistry } from "@pmt/llm";

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

  try {
    await loadStoredProviders(registry);
  } catch (err) {
    console.error("[lifecycle] failed to load stored providers:", err);
  }

  // Load proxy configuration from database or environment
  let proxyUrl: string | undefined = process.env.https_proxy || process.env.HTTPS_PROXY;
  if (proxyUrl) {
    console.log(`[lifecycle] Using proxy from environment: ${proxyUrl}`);
  }

  // Also check database for proxy config (can override env)
  try {
    const proxyRow = db.prepare("SELECT value FROM filter_config WHERE key = 'proxy_config'").get() as { value: string } | undefined;
    if (proxyRow) {
      const proxyConfig = JSON.parse(proxyRow.value) as { enabled: boolean; httpsProxy: string };
      if (proxyConfig.enabled && proxyConfig.httpsProxy) {
        proxyUrl = proxyConfig.httpsProxy;
        console.log(`[lifecycle] Using proxy from database: ${proxyUrl}`);
      }
    }
  } catch {
    // Ignore proxy config errors
  }

  // Use default proxy if none configured
  if (!proxyUrl) {
    const defaultProxy = "http://127.0.0.1:7890";
    proxyUrl = defaultProxy;
    console.log(`[lifecycle] Using default proxy: ${proxyUrl}`);
    
    // Save default config to database for UI consistency
    try {
      const defaultConfig = { enabled: true, httpProxy: defaultProxy, httpsProxy: defaultProxy };
      db.prepare(
        "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
      ).run("proxy_config", JSON.stringify(defaultConfig), Date.now(), "default");
      console.log(`[lifecycle] Default proxy config saved to database`);
    } catch (err) {
      console.error(`[lifecycle] Failed to save default proxy config:`, err);
    }
  }

  // Set proxy URL in config for collector HTTP fallback
  config.proxyUrl = proxyUrl;

  const executor = createExecutor({
    config,
    bus,
    signalRepo,
    portfolioRepo,
    logger: noopLogger,
  });

  console.log(`[lifecycle] Creating collector with proxyUrl: ${proxyUrl || 'none'}`);
  
  const collector = createCollector({
    config,
    bus,
    executor,
    wsClientFactory: (onTrade) =>
      createPolymarketWsClient({
        // Use Activity WebSocket (RTDS) for trade activity stream
        url: config.polymarketActivityWsUrl,
        onTrade,
        onError: (err) => console.error(`[ws-activity] ${err.message}`),
        ...(proxyUrl ? { proxyUrl } : {}),
      }),
    // Temporarily disable CLOB WebSocket due to connection issues
    // clobWsClientFactory: (onPriceUpdate) =>
    //   createClobWsClient({
    //     url: config.polymarketClobWsUrl,
    //     onPriceUpdate,
    //     onError: (err) => console.error(`[ws-clob] ${err.message}`),
    //     ...(proxyUrl ? { proxyUrl } : {}),
    //   }),
    marketMetadataProvider: createRealMarketMetadataProvider(proxyUrl),
    logger: console,
  });

  // Set up Analyzer LLM integration
  setAnalyzerCallback(async (trigger: TriggerEvent): Promise<VerdictEvent | null> => {
    const assigned = registry.getProviderForAgent("analyzer");
    if (!assigned) {
      console.warn("[lifecycle] No LLM provider available for analyzer");
      return null;
    }

    try {
      const prompt = packContext(trigger);
      const response = await assigned.provider.chat({
        model: assigned.modelId,
        messages: [
          { role: "system", content: getAnalyzerSystemPrompt() },
          { role: "user", content: prompt },
        ],
        temperature: 0.3,
        maxTokens: 500,
      });

      if (!response) return null;

      const parsed = parseVerdict(response.content);
      
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
      console.error("[lifecycle] Analyzer LLM error:", err);
      return null;
    }
  });

  // Connect EventBus flow: Trigger -> Analyzer -> Verdict -> Executor
  // Step 1: Subscribe to Triggers, send to Analyzer
  bus.onTrigger(async (trigger) => {
    const analyzerCb = getAnalyzerCallback();
    if (!analyzerCb) {
      console.warn("[lifecycle] No analyzer callback registered");
      return;
    }
    try {
      const verdict = await analyzerCb(trigger);
      if (verdict) {
        bus.publishVerdict(verdict);
        console.log(`[lifecycle] Analyzer verdict: ${verdict.verdict} for ${trigger.market_id}`);
      }
    } catch (err) {
      console.error("[lifecycle] Analyzer error:", err);
    }
  });

  // Step 2: Subscribe to Verdicts, send to Executor
  bus.onVerdict((verdict) => {
    executor.handleVerdict(verdict);
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

function getAnalyzerSystemPrompt(): string {
  return `You are the Polymarket Analyzer. Your job is to assess trading signals.

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

    console.log("[lifecycle] Applied", rows.length, "config overrides from database");
  } catch (err) {
    console.error("[lifecycle] Failed to load config overrides from database:", err);
  }
  return config;
}

/**
 * Reconnect any LLM providers whose API keys are already stored in the
 * secrets store. Each provider is wrapped in its own try/catch so that a
 * single bad credential never blocks the rest of the app from booting.
 */
async function loadStoredProviders(registry: ProviderRegistry): Promise<void> {
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
      }
      if (provider) {
        await provider.connect();
        registry.register(provider);
      }
    } catch (err) {
      console.error(`[lifecycle] failed to reconnect ${providerId}:`, err);
    }
  }
}
