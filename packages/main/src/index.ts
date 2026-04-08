/**
 * @pmt/main — Electron main process entry.
 *
 * M3 wiring: engine + tray + window + schedulers. No IPC, no LLM until M5.
 */
import { app } from "electron";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { bootEngine, shutdownEngine, getEngineContext } from "./lifecycle.js";
import { registerIpcHandlers } from "./ipc.js";
import { createTray, type TrayHandle } from "./tray.js";
import { createMainWindow, type WindowHandle } from "./window.js";
import {
  createReviewerScheduler,
  type ReviewerScheduler,
} from "./reviewer-scheduler.js";
import {
  createCoordinatorScheduler,
  type CoordinatorScheduler,
} from "./coordinator.js";
import { runReviewer } from "@pmt/engine/reviewer";
import {
  createSignalLogRepo,
  createStrategyPerformanceRepo,
} from "@pmt/engine";
import { createRiskMgrRunner } from "@pmt/llm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const preloadPath = join(__dirname, "preload.js");
const isDev = process.env.NODE_ENV === "development";
const rendererUrl = isDev
  ? process.env.VITE_DEV_SERVER_URL ?? "http://localhost:5173"
  : join(__dirname, "..", "..", "renderer", "dist", "index.html");

let mainWindow: WindowHandle | null = null;
let tray: TrayHandle | null = null;
let reviewerScheduler: ReviewerScheduler | null = null;
let coordinatorScheduler: CoordinatorScheduler | null = null;

const noopLogger = {
  info: (_m: string): void => {},
  warn: (_m: string): void => {},
  error: (_m: string): void => {},
};

async function onReady(): Promise<void> {
  const ctx = await bootEngine();

  mainWindow = createMainWindow({ preloadPath, rendererUrl, isDev });

  tray = createTray({
    iconPath: undefined,
    onShowWindow: () => mainWindow?.show(),
    onQuit: () => {
      (app as unknown as Record<string, unknown>).isQuittingExplicit = true;
      app.quit();
    },
  });

  // Reviewer scheduler — daily
  reviewerScheduler = createReviewerScheduler({
    runReviewer: async () => {
      const result = await runReviewer({
        db: ctx.db,
        config: ctx.config,
        signalRepo: createSignalLogRepo(ctx.db),
        strategyPerfRepo: createStrategyPerformanceRepo(ctx.db),
        logger: noopLogger,
      });
      return {
        bucketCount: result.bucketCount,
        killSwitches: result.killSwitches,
        reportPath: result.reportPath,
      };
    },
    lastRunAt: () => {
      const row = ctx.db
        .prepare("SELECT value FROM app_state WHERE key = ?")
        .get("reviewer_last_run") as { value: string } | undefined;
      return row ? Number(row.value) : null;
    },
    onRun: () => {
      ctx.db
        .prepare(
          "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"
        )
        .run("reviewer_last_run", String(Date.now()), Date.now());
    },
  });
  reviewerScheduler.start();

  // Coordinator scheduler — hourly
  const riskMgrRunner = createRiskMgrRunner({ registry: ctx.registry });
  coordinatorScheduler = createCoordinatorScheduler({
    intervalMs: 60 * 60 * 1000,
    generateBrief: async () => {
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
      const recentTradeRows = ctx.db
        .prepare(
          "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
        )
        .all() as Array<{
        market_title: string;
        direction: string;
        pnl_net_usdc: number | null;
        exit_reason: string | null;
      }>;
      const openCount = ctx.db
        .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
        .get() as { n: number };

      return riskMgrRunner.generateBrief({
        windowMs: 60 * 60 * 1000,
        systemState: {
          portfolioState: {
            current_equity: Number(portfolioState.current_equity ?? 10000),
            day_start_equity: Number(portfolioState.day_start_equity ?? 10000),
            daily_halt_triggered: Boolean(
              portfolioState.daily_halt_triggered ?? false
            ),
          },
          recentTrades: recentTradeRows,
          openPositionCount: openCount.n,
        },
      });
    },
    onBrief: (brief) => {
      ctx.db
        .prepare(
          "INSERT INTO coordinator_log (generated_at, summary, alerts, suggestions, context_snapshot, model_used) VALUES (?, ?, ?, ?, ?, ?)"
        )
        .run(
          Date.now(),
          brief.summary,
          JSON.stringify(brief.alerts),
          JSON.stringify(brief.suggestions),
          "{}",
          ""
        );
    },
  });
  coordinatorScheduler.start();

  registerIpcHandlers({
    getEngineContext,
    getRiskMgrRunner: () => riskMgrRunner,
  });

  // Start collector (engine WS subscription)
  await ctx.collector.start();

  mainWindow.show();
}

if (process.env.VITEST !== "true") {
  app
    .whenReady()
    .then(onReady)
    .catch((err) => {
      console.error("[pmt-main] failed to start:", err);
      app.quit();
    });

  app.on("window-all-closed", () => {
    // tray keeps app alive
  });

  app.on("before-quit", async () => {
    reviewerScheduler?.stop();
    coordinatorScheduler?.stop();
    await shutdownEngine();
  });

  app.on("activate", () => {
    mainWindow?.show();
  });
}

export const PACKAGE_NAME = "@pmt/main";
