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
  type EventBus,
  type Collector,
  type Executor,
  type TraderConfig,
  type MarketMetadata,
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
 * Placeholder market-metadata provider used at boot time.
 *
 * Returns a deterministic stub for any market_id so the collector can run end
 * to end without crashing on first trade. The stub uses the market_id as the
 * title, sets a 24h expiry, and a $10k liquidity hint — enough for the
 * trigger evaluator and analyzer prompts to format something coherent during
 * paper trading. M5 wires the real Polymarket Gamma REST client and replaces
 * this provider.
 *
 * IMPORTANT: never throw here — the collector calls this on every trade for
 * an unseen market, and a throwing provider takes the entire pipeline down.
 */
async function placeholderMarketMetadataProvider(
  marketId: string
): Promise<MarketMetadata> {
  return {
    marketId,
    marketTitle: marketId,
    resolvesAt: Date.now() + 86_400_000,
    liquidity: 10_000,
  };
}

/**
 * Boot the engine. Idempotent: returns the existing context if already booted.
 */
export async function bootEngine(): Promise<EngineContext> {
  if (activeContext) return activeContext;

  const dataDir = resolveDataDir();
  const dbPath = join(dataDir, "data.db");
  const db = openDatabase(dbPath);

  const config = loadConfig(undefined);
  const signalRepo = createSignalLogRepo(db);
  const portfolioRepo = createPortfolioStateRepo(db);
  const bus = createEventBus();
  const registry = createProviderRegistry();

  try {
    await loadStoredProviders(registry);
  } catch (err) {
    console.error("[lifecycle] failed to load stored providers:", err);
  }

  // Load proxy configuration from database
  let proxyUrl: string | undefined;
  try {
    const proxyRow = db.prepare("SELECT value FROM filter_config WHERE key = 'proxy_config'").get() as { value: string } | undefined;
    if (proxyRow) {
      const proxyConfig = JSON.parse(proxyRow.value) as { enabled: boolean; httpsProxy: string };
      if (proxyConfig.enabled && proxyConfig.httpsProxy) {
        proxyUrl = proxyConfig.httpsProxy;
        console.log(`[lifecycle] Using proxy: ${proxyUrl}`);
      }
    }
  } catch {
    // Ignore proxy config errors
  }

  const collector = createCollector({
    config,
    bus,
    wsClientFactory: (onTrade) =>
      createPolymarketWsClient({
        url: config.polymarketWsUrl,
        onTrade,
        onError: (err) => noopLogger.error(`[ws] ${err.message}`),
        proxyUrl,
      }),
    marketMetadataProvider: placeholderMarketMetadataProvider,
    logger: noopLogger,
  });

  const executor = createExecutor({
    config,
    bus,
    signalRepo,
    portfolioRepo,
    logger: noopLogger,
  });

  activeContext = {
    db,
    dbPath,
    config,
    bus,
    collector,
    executor,
    registry,
  };
  return activeContext;
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
