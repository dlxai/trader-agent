/**
 * Polymarket Trader plugin entry point.
 *
 * Wires together all M1-M3 modules: Collector (WS + rolling stats + trigger),
 * Executor (Kelly + circuit breakers + four-route exit), Analyzer (LLM bridge).
 *
 * See docs/specs/2026-04-06-polymarket-trading-agents-design.md for the
 * full design and docs/plans/I1-I2-findings.md for the OpenClaw integration
 * approach (cron + polling for agent invocation).
 */
import { definePlugin } from "./plugin-sdk.js";
import type { PluginApi } from "./plugin-sdk.js";
import { homedir } from "node:os";
import { join } from "node:path";
import { openDatabase } from "./db/connection.js";
import { createSignalLogRepo } from "./db/signal-log-repo.js";
import { createPortfolioStateRepo } from "./db/portfolio-state-repo.js";
import { loadConfig } from "./config/loader.js";
import { createEventBus } from "./bus/events.js";
import { createCollector } from "./collector/collector.js";
import { createExecutor } from "./executor/executor.js";
import { createAnalyzerClient } from "./analyzer/analyzer-client.js";
import type { AgentInvoker } from "./analyzer/analyzer-client.js";
import { packContext } from "./analyzer/context-packer.js";
import { createPolymarketWsClient } from "./collector/ws-client.js";
import { performStartupRecovery } from "./recovery/startup-recovery.js";

// POLYMARKET_TRADER_HOME isolation: see Isolation Setup section in plan.
// Defaults to ~/.polymarket-trader/ which is fully separate from ~/.openclaw/.
const POLYMARKET_TRADER_HOME =
  process.env.POLYMARKET_TRADER_HOME?.trim() || join(homedir(), ".polymarket-trader");
const DEFAULT_DB_PATH = join(POLYMARKET_TRADER_HOME, "data.db");

// Module-level state survives double activation (the OpenClaw runtime may
// call register/activate twice during gateway restart).
let started = false;
let cleanup: (() => void) | null = null;

interface MinimalLogger {
  info: (m: string) => void;
  warn: (m: string) => void;
  error: (m: string) => void;
}

function adaptLogger(api: PluginApi): MinimalLogger {
  return {
    info: (m) => api.logger.info(m),
    warn: (m) => api.logger.warn(m),
    error: (m) => (api.logger.error ?? api.logger.warn)(m),
  };
}

export default definePlugin({
  id: "polymarket-trader",
  name: "Polymarket Trader",

  setup(api: PluginApi) {
    if (started) {
      api.logger.info("[polymarket] already started, skipping re-activation");
      return;
    }
    started = true;
    api.logger.info("[polymarket] activating...");

    const logger = adaptLogger(api);
    const config = loadConfig(undefined);
    const db = openDatabase(DEFAULT_DB_PATH);
    const signalRepo = createSignalLogRepo(db);
    const portfolioRepo = createPortfolioStateRepo(db);

    performStartupRecovery({
      signalRepo,
      portfolioRepo,
      nowMs: Date.now(),
      logger,
    });

    const bus = createEventBus();

    // Agent invoker placeholder. Per docs/plans/I1-I2-findings.md, the real
    // implementation will use the OpenClaw cron API (cron.run + cron.runs
    // polling) to invoke the polymarket-analyzer agent. For Task 28 we wire
    // a stub that throws so the plugin loads cleanly but Analyzer calls fail
    // loudly until the cron-based invoker is implemented in a follow-up task.
    const invoker: AgentInvoker = async (_agentId, _message) => {
      throw new Error(
        "AgentInvoker not implemented yet — wire OpenClaw cron API per I1 findings"
      );
    };
    const analyzerClient = createAnalyzerClient({
      agentId: "polymarket-analyzer",
      timeoutMs: config.llmTimeoutMs,
      invoker,
    });

    // Market metadata provider stub. For M1 it returns synthetic metadata so
    // the trigger pipeline can run end-to-end without a real Polymarket Gamma
    // API client. M2 will replace this with a real fetch.
    const marketMetadataProvider = async (marketId: string) => {
      return {
        marketId,
        marketTitle: marketId,
        resolvesAt: Date.now() + 86_400_000,
        liquidity: 10_000,
      };
    };

    const collector = createCollector({
      config,
      bus,
      wsClientFactory: (onTrade) =>
        createPolymarketWsClient({
          url: config.polymarketWsUrl,
          onTrade,
          onError: (err) => logger.warn(`[polymarket-ws] ${err.message}`),
        }),
      marketMetadataProvider,
      logger,
    });

    const executor = createExecutor({
      config,
      bus,
      signalRepo,
      portfolioRepo,
      logger,
    });

    // Wire trigger -> Analyzer -> Executor
    bus.onTrigger(async (trigger) => {
      try {
        const prompt = packContext(trigger);
        const parsed = await analyzerClient.judge(prompt);
        executor.handleVerdict({
          type: "verdict",
          trigger,
          verdict: parsed.verdict,
          confidence: parsed.confidence,
          reasoning: parsed.reasoning,
          llm_direction: parsed.direction,
        });
      } catch (err) {
        logger.warn(`[polymarket] analyzer error: ${String(err)}`);
      }
    });

    collector.start().catch((err) => {
      logger.error(`[polymarket] collector failed to start: ${String(err)}`);
    });

    cleanup = () => {
      try {
        collector.stop();
        db.close();
      } catch (err) {
        logger.warn(`[polymarket] cleanup error: ${String(err)}`);
      }
    };

    api.logger.info("[polymarket] activated");
  },
});

/** Test-only escape hatch. Used by tests that need to reset module state. */
export function __testCleanup(): void {
  cleanup?.();
  cleanup = null;
  started = false;
}
