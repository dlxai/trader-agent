/**
 * Polymarket Trader - OpenClaw Plugin Entry
 */
import { definePlugin, type PluginContext } from "./plugin-sdk.js";
import { createCollector } from "./collector/collector.js";
import { createExecutor } from "./executor/executor.js";
import { openDatabase } from "./db/connection.js";
import { createEventBus } from "./bus/events.js";
import { loadConfig } from "./config/loader.js";
import { runReviewer } from "./reviewer/reviewer.js";
import { createSignalLogRepo } from "./db/signal-log-repo.js";
import { createStrategyPerformanceRepo } from "./db/strategy-performance-repo.js";
import { createPortfolioStateRepo } from "./db/portfolio-state-repo.js";
import { performStartupRecovery } from "./recovery/startup-recovery.js";
import { createPolymarketWsClient } from "./collector/ws-client.js";
import { createClobWsClient } from "./collector/clob-ws-client.js";
import { createPolymarketMarketMetadataProvider } from "./collector/polymarket-api.js";
import { packContext, parseVerdict } from "./analyzer/index.js";
import type { TriggerEvent, VerdictEvent } from "./bus/types.js";
import type { TraderConfig } from "./config/schema.js";
import type Database from "better-sqlite3";

// Re-export all modules for use by other packages
export * from "./collector/index.js";
export * from "./executor/index.js";
export * from "./db/index.js";
export * from "./bus/index.js";
export * from "./config/index.js";
export * from "./reviewer/index.js";
export * from "./recovery/index.js";
export * from "./analyzer/index.js";
export * from "./util/index.js";
export * from "./plugin-sdk.js";

// Plugin state
let collector: ReturnType<typeof createCollector> | null = null;
let executor: ReturnType<typeof createExecutor> | null = null;
let db: Database.Database | null = null;
let config: TraderConfig | null = null;
let bus: ReturnType<typeof createEventBus> | null = null;

// External Analyzer callback - set by main package to provide LLM integration
let analyzerCallback: ((trigger: TriggerEvent) => Promise<VerdictEvent | null>) | null = null;

/**
 * Set the external Analyzer callback for LLM processing.
 * This should be called by the main package after plugin activation.
 */
export function setAnalyzerCallback(
  callback: (trigger: TriggerEvent) => Promise<VerdictEvent | null>
): void {
  analyzerCallback = callback;
}

/**
 * Get the current Analyzer callback.
 */
export function getAnalyzerCallback(): ((trigger: TriggerEvent) => Promise<VerdictEvent | null>) | null {
  return analyzerCallback;
}

/**
 * Get the current event bus for external use (e.g., Analyzer integration)
 */
export function getEventBusForExternal(): ReturnType<typeof createEventBus> | null {
  return bus;
}

/**
 * Get the current database instance (for use by other modules)
 */
export function getDatabase(): Database.Database | null {
  return db;
}

/**
 * Get the current config (for use by other modules)
 */
export function getConfig(): TraderConfig | null {
  return config;
}

/**
 * Get the collector instance
 */
export function getCollector(): ReturnType<typeof createCollector> | null {
  return collector;
}

/**
 * Get the executor instance
 */
export function getExecutor(): ReturnType<typeof createExecutor> | null {
  return executor;
}

/**
 * Get the event bus instance
 */
export function getEventBus(): ReturnType<typeof createEventBus> | null {
  return bus;
}

export default definePlugin({
  id: "polymarket-trader",
  name: "Polymarket Trader",
  version: "0.2.0",

  async activate(context: PluginContext) {
    const { logger, workspaceDir } = context;

    logger.info("[polymarket-trader] Activating plugin...");

    // Initialize database
    const dbPath = process.env.POLYMARKET_TRADER_DB || `${workspaceDir}/data.db`;
    db = openDatabase(dbPath);
    logger.info(`[polymarket-trader] Database initialized at ${dbPath}`);

    // Create event bus
    bus = createEventBus();

    // Create repositories
    const signalRepo = createSignalLogRepo(db);
    const portfolioRepo = createPortfolioStateRepo(db);
    const strategyPerfRepo = createStrategyPerformanceRepo(db);

    // Load configuration
    config = loadConfig(undefined);
    logger.info("[polymarket-trader] Configuration loaded");

    // Perform startup recovery
    const recovery = performStartupRecovery({
      signalRepo,
      portfolioRepo,
      nowMs: Date.now(),
      logger,
    });
    logger.info(`[polymarket-trader] Startup recovery: ${recovery.openPositionCount} positions loaded, dailyReset=${recovery.dailyHaltReset}, weeklyReset=${recovery.weeklyHaltReset}`);

    // Initialize executor
    executor = createExecutor({
      config,
      bus,
      signalRepo,
      portfolioRepo,
      logger,
    });

    // Set up Analyzer integration: subscribe to triggers, call external LLM
    bus.onTrigger(async (trigger) => {
      if (analyzerCallback) {
        try {
          const verdict = await analyzerCallback(trigger);
          if (verdict && bus) {
            bus.publishVerdict(verdict);
            logger.info(`[analyzer] Verdict received for ${trigger.market_id}: ${verdict.verdict}`);
          }
        } catch (err) {
          logger.error(`[analyzer] Error processing trigger: ${String(err)}`);
        }
      } else {
        // No LLM configured - signal is dropped (production behavior)
        logger.warn(`[analyzer] No LLM callback registered, signal dropped for ${trigger.market_id}`);
      }
    });

    // Set up Executor: subscribe to verdicts and execute trades
    bus.onVerdict((verdict) => {
      if (executor) {
        executor.handleVerdict(verdict);
      }
    });

    // Initialize collector with real market metadata provider
    // Uses Activity WebSocket (RTDS) for trade activity stream
    // Uses CLOB WebSocket for position price monitoring
    const currentConfig = config; // capture for closure
    collector = createCollector({
      config: currentConfig,
      bus,
      executor,
      wsClientFactory: (onTrade) =>
        createPolymarketWsClient({
          url: currentConfig.polymarketActivityWsUrl,
          onTrade,
          onError: (err) => logger.error(`[ws-activity] ${err.message}`),
        }),
      clobWsClientFactory: (onPriceUpdate) =>
        createClobWsClient({
          url: currentConfig.polymarketClobWsUrl,
          onPriceUpdate,
          onError: (err) => logger.error(`[ws-clob] ${err.message}`),
        }),
      marketMetadataProvider: createPolymarketMarketMetadataProvider(),
      logger,
    });

    // Start collector
    await collector.start();
    logger.info("[polymarket-trader] Collector started with Analyzer LLM integration");

    // Register Reviewer cron job (daily at 00:00)
    context.cron.register("reviewer-daily", "0 0 * * *", async () => {
      logger.info("[polymarket-trader] Running daily reviewer...");
      try {
        if (!db || !config) {
          logger.error("[polymarket-trader] Database or config not available");
          return;
        }
        const result = await runReviewer({
          db,
          config,
          signalRepo: createSignalLogRepo(db),
          strategyPerfRepo: createStrategyPerformanceRepo(db),
          logger,
        });
        logger.info(`[polymarket-trader] Reviewer completed: ${result.bucketCount} buckets analyzed, ${result.killSwitches} kill switches`);
      } catch (err) {
        logger.error(`[polymarket-trader] Reviewer failed: ${String(err)}`);
      }
    });

    // Register Coordinator cron job (hourly)
    context.cron.register("coordinator-hourly", "0 * * * *", async () => {
      logger.info("[polymarket-trader] Running hourly coordinator...");
      // Coordinator logic will be implemented in main package
      context.events.emit("coordinator:run", { timestamp: Date.now() });
    });

    logger.info("[polymarket-trader] Plugin activated successfully");
  },

  async deactivate() {
    if (collector) {
      collector.stop();
    }
    if (db) {
      db.close();
    }
  },
});
