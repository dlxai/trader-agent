import type Database from "better-sqlite3";
import type { TraderConfig } from "../config/schema.js";
import type { SignalLogRepo } from "../db/signal-log-repo.js";
import type { StrategyPerformanceRepo } from "../db/strategy-performance-repo.js";
import { computeBucketStats } from "./statistics.js";
import { decideKillSwitch } from "./kill-switch-decider.js";
import { generateReport } from "./report-generator.js";
import { writeFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface ReviewerDeps {
  db: Database.Database;
  config: TraderConfig;
  signalRepo: SignalLogRepo;
  strategyPerfRepo: StrategyPerformanceRepo;
  logger: { info: (m: string) => void; warn: (m: string) => void; error: (m: string) => void };
}

export interface ReviewerRunResult {
  bucketCount: number;
  killSwitches: number;
  reportPath: string;
}

export async function runReviewer(deps: ReviewerDeps): Promise<ReviewerRunResult> {
  const nowMs = Date.now();
  const windowMs = 7 * 24 * 3600 * 1000;
  const trades = deps.signalRepo.listClosedSince(nowMs - windowMs);

  const buckets = computeBucketStats(trades, { windowMs, nowMs });

  for (const b of buckets) {
    deps.strategyPerfRepo.upsert({
      price_bucket: b.price_bucket,
      window: "7d",
      trade_count: b.trade_count,
      win_count: b.win_count,
      win_rate: b.win_rate,
      total_pnl_net_usdc: b.total_pnl_net_usdc,
      last_updated: nowMs,
    });
  }

  const aggregate = buckets.reduce(
    (acc, b) => ({
      trade_count: acc.trade_count + b.trade_count,
      win_count: acc.win_count + b.win_count,
      win_rate: 0,
      total_pnl_net_usdc: acc.total_pnl_net_usdc + b.total_pnl_net_usdc,
    }),
    { trade_count: 0, win_count: 0, win_rate: 0, total_pnl_net_usdc: 0 }
  );
  aggregate.win_rate = aggregate.trade_count > 0 ? aggregate.win_count / aggregate.trade_count : 0;
  const killDecision = decideKillSwitch(aggregate, deps.config);

  const killSwitches: Array<{ strategy: string; reason: string }> = [];
  if (killDecision.kill) {
    killSwitches.push({ strategy: "smart_money_flow", reason: killDecision.reason ?? "unknown" });
  }

  const totalPnl7d = aggregate.total_pnl_net_usdc;
  const markdown = generateReport({
    period: "weekly",
    nowMs,
    buckets7d: buckets,
    killSwitches,
    totalPnl7d,
  });

  const reportsDir =
    process.env.POLYMARKET_TRADER_HOME?.trim()
      ? join(process.env.POLYMARKET_TRADER_HOME, "reports")
      : join(homedir(), ".polymarket-trader", "reports");
  mkdirSync(reportsDir, { recursive: true });
  const reportPath = join(reportsDir, `review-${new Date(nowMs).toISOString().slice(0, 10)}.md`);
  writeFileSync(reportPath, markdown, "utf-8");
  deps.logger.info(`[reviewer] report written to ${reportPath}`);

  return {
    bucketCount: buckets.length,
    killSwitches: killSwitches.length,
    reportPath,
  };
}
