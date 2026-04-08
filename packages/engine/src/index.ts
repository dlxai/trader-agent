/**
 * Polymarket Trader - OpenClaw Plugin Entry
 */
import { definePlugin, type PluginContext } from "./plugin-sdk.js";
import { createCollector } from "./collector/collector.js";
import { createExecutor } from "./executor/executor.js";
import { openDatabase } from "./db/connection.js";
import { runMigrations } from "./db/migrations.js";
import { loadConfig } from "./config/loader.js";
import { runReviewer } from "./reviewer/reviewer.js";
import { createSignalLogRepo } from "./db/signal-log-repo.js";
import { createStrategyPerformanceRepo } from "./db/strategy-performance-repo.js";
import { performStartupRecovery } from "./recovery/startup-recovery.js";
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

export default definePlugin({
  id: "polymarket-trader",
  name: "Polymarket Trader",
  version: "0.2.0",

  async activate(context: PluginContext) {
    const { logger, config: pluginConfig, workspaceDir } = context;

    logger.info("[polymarket-trader] Activating plugin...");

    // Initialize database
    const dbPath = process.env.POLYMARKET_TRADER_DB || `${workspaceDir}/data.db`;
    db = openDatabase(dbPath);
    runMigrations(db);
    logger.info(`[polymarket-trader] Database initialized at ${dbPath}`);

    // Load configuration
    config = loadConfig(db);
    logger.info("[polymarket-trader] Configuration loaded");

    // Perform startup recovery
    const recovery = performStartupRecovery(db, logger);
    logger.info(`[polymarket-trader] Startup recovery: ${recovery.openPositionsRecovered} positions recovered`);

    // Initialize executor
    executor = createExecutor({
      db,
      config,
      onError: (err) => logger.error(`[executor] ${String(err)}`),
    });

    // Initialize collector
    collector = createCollector({
      db,
      config,
      executor,
      logger,
    });

    // Start collector
    await collector.start();
    logger.info("[polymarket-trader] Collector started");

    // Register Reviewer cron job (daily at 00:00)
    context.cron.register("reviewer-daily", "0 0 * * *", async () => {
      logger.info("[polymarket-trader] Running daily reviewer...");
      try {
        const result = await runReviewer({
          db,
          config,
          signalRepo: createSignalLogRepo(db),
          strategyPerfRepo: createStrategyPerformanceRepo(db),
          logger,
        });
        logger.info(`[polymarket-trader] Reviewer completed: ${result.bucketCount} buckets analyzed`);
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
