import type { BucketStats } from "./statistics.js";

export interface ReportInput {
  period: "daily" | "weekly";
  nowMs: number;
  buckets7d: BucketStats[];
  killSwitches: Array<{ strategy: string; reason: string }>;
  totalPnl7d: number;
}

export function generateReport(input: ReportInput): string {
  const lines: string[] = [];
  const date = new Date(input.nowMs).toISOString().slice(0, 10);
  lines.push(`# Polymarket Reviewer Report`);
  lines.push(``);
  lines.push(`**Period:** ${input.period}`);
  lines.push(`**Generated:** ${date}`);
  lines.push(`**7-day net PnL:** $${input.totalPnl7d.toFixed(2)}`);
  lines.push(``);

  if (input.killSwitches.length > 0) {
    lines.push(`## [ALERT] Kill switches fired`);
    lines.push(``);
    for (const k of input.killSwitches) {
      lines.push(`- **${k.strategy}**: ${k.reason}`);
    }
    lines.push(``);
  }

  lines.push(`## Per-bucket performance (7d)`);
  lines.push(``);
  lines.push(`| Bucket | Trades | Wins | Win rate | Net PnL |`);
  lines.push(`|--------|--------|------|----------|---------|`);
  for (const b of input.buckets7d) {
    lines.push(
      `| ${b.price_bucket.toFixed(2)} | ${b.trade_count} | ${b.win_count} | ${(b.win_rate * 100).toFixed(1)}% | $${b.total_pnl_net_usdc.toFixed(2)} |`
    );
  }
  lines.push(``);

  return lines.join("\n");
}
