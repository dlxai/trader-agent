import type { ProviderRegistry } from "../registry.js";
import { REVIEWER_SYSTEM_PROMPT } from "./personas/reviewer.js";

export interface BucketStat {
  price_bucket: number;
  trade_count: number;
  win_count: number;
  win_rate: number;
  total_pnl_net_usdc: number;
}

export interface KillSwitchSummary {
  strategy: string;
  reason: string;
}

export interface ReviewerInput {
  period: "daily" | "weekly";
  totalPnl7d: number;
  bucketStats: BucketStat[];
  killSwitches: KillSwitchSummary[];
}

export interface ReviewerRunner {
  generateCommentary(input: ReviewerInput): Promise<string>;
}

function buildPrompt(input: ReviewerInput): string {
  const lines: string[] = [];
  lines.push(`Period: ${input.period}`);
  lines.push(`7-day net PnL: $${input.totalPnl7d.toFixed(2)}`);
  lines.push(``);
  lines.push(`Per-bucket stats:`);
  for (const b of input.bucketStats) {
    lines.push(
      `- bucket ${b.price_bucket.toFixed(2)}: ${b.trade_count} trades, ${b.win_count} wins (${(b.win_rate * 100).toFixed(1)}%), net $${b.total_pnl_net_usdc.toFixed(2)}`
    );
  }
  if (input.killSwitches.length > 0) {
    lines.push(``);
    lines.push(`Kill switches fired:`);
    for (const k of input.killSwitches) {
      lines.push(`- ${k.strategy}: ${k.reason}`);
    }
  }
  return lines.join("\n");
}

export function createReviewerRunner(opts: { registry: ProviderRegistry }): ReviewerRunner {
  return {
    async generateCommentary(input: ReviewerInput): Promise<string> {
      const assigned = opts.registry.getProviderForAgent("reviewer");
      if (!assigned) return "";

      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: REVIEWER_SYSTEM_PROMPT },
            { role: "user", content: buildPrompt(input) },
          ],
          temperature: 0.5,
          maxTokens: 800,
        });
        return resp.content;
      } catch {
        return "";
      }
    },
  };
}
