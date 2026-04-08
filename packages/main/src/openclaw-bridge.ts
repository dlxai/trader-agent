/**
 * OpenClaw Bridge - Connects OpenClaw plugin to Electron UI
 */
import type { PluginContext } from "@pmt/engine";
import type { CoordinatorBrief } from "@pmt/llm";
import { createRiskMgrRunner } from "@pmt/llm";
import { getDatabase, getConfig, getCollector } from "@pmt/engine";
import { showNotification } from "./notifications.js";

// Event emitter for UI updates
type EventHandler = (data: unknown) => void;
const eventHandlers: Map<string, EventHandler[]> = new Map();

export const openclawBridge = {
  // Called when OpenClaw plugin activates
  onPluginActivate(context: PluginContext) {
    console.log("[openclaw-bridge] Plugin activated");

    // Listen for coordinator events from plugin
    context.events.on("coordinator:run", async (data) => {
      console.log("[openclaw-bridge] Coordinator run triggered", data);

      const db = getDatabase();
      const config = getConfig();

      if (!db || !config) {
        console.error("[openclaw-bridge] Database or config not available");
        return;
      }

      // Generate brief using RiskMgrRunner
      const registry = (global as unknown as Record<string, unknown>).llmRegistry as
        | { getProviderForAgent: (agentId: string) => { provider: unknown; modelId: string } | null }
        | undefined;

      if (!registry) {
        console.error("[openclaw-bridge] LLM registry not available");
        return;
      }

      const riskMgrRunner = createRiskMgrRunner({ registry });

      const portfolioRows = db
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

      const recentTradeRows = db
        .prepare(
          "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
        )
        .all() as Array<{
        market_title: string;
        direction: string;
        pnl_net_usdc: number | null;
        exit_reason: string | null;
      }>;

      const openCount = db
        .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
        .get() as { n: number };

      try {
        const brief = await riskMgrRunner.generateBrief({
          windowMs: 60 * 60 * 1000,
          systemState: {
            portfolioState: {
              current_equity: Number(portfolioState.current_equity ?? 10000),
              day_start_equity: Number(portfolioState.day_start_equity ?? 10000),
              daily_halt_triggered: Boolean(portfolioState.daily_halt_triggered ?? false),
            },
            recentTrades: recentTradeRows,
            openPositionCount: openCount.n,
          },
        });

        // Persist to database
        db.prepare(
          "INSERT INTO coordinator_log (generated_at, summary, alerts, suggestions, context_snapshot, model_used) VALUES (?, ?, ?, ?, ?, ?)"
        ).run(
          Date.now(),
          brief.summary,
          JSON.stringify(brief.alerts),
          JSON.stringify(brief.suggestions),
          "{}",
          ""
        );

        // Show notifications
        for (const alert of brief.alerts) {
          if (alert.severity === "critical") {
            showNotification({
              title: "Polymarket Trader: Critical Alert",
              body: alert.text,
            });
          } else if (alert.severity === "warning") {
            showNotification({
              title: "Polymarket Trader: Warning",
              body: alert.text,
              silent: true,
            });
          }
        }

        // Emit to UI
        openclawBridge.emitToUI("coordinator:brief", brief);
      } catch (err) {
        console.error("[openclaw-bridge] Coordinator failed:", err);
      }
    });

    // Store context for later use
    (global as unknown as Record<string, unknown>).openclawContext = context;
  },

  // Emit event to UI
  emitToUI(event: string, data: unknown) {
    const handlers = eventHandlers.get(event);
    if (handlers) {
      handlers.forEach((h) => h(data));
    }
  },

  // Subscribe to events from UI
  onUIEvent(event: string, handler: EventHandler) {
    if (!eventHandlers.has(event)) {
      eventHandlers.set(event, []);
    }
    eventHandlers.get(event)!.push(handler);
    return () => {
      const handlers = eventHandlers.get(event);
      if (handlers) {
        const idx = handlers.indexOf(handler);
        if (idx > -1) handlers.splice(idx, 1);
      }
    };
  },

  // Get OpenClaw context
  getContext(): PluginContext | undefined {
    return (global as unknown as Record<string, unknown>).openclawContext as
      | PluginContext
      | undefined;
  },
};
