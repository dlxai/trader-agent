import { describe, it, expect, vi } from "vitest";
import { createReviewerRunner } from "../../src/runners/reviewer-runner.js";
import type { LlmProvider } from "../../src/types.js";

function makeProvider(content: string): LlmProvider {
  return {
    id: "anthropic_api" as any,
    authType: "api_key",
    displayName: "test",
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => [{ id: "m", contextWindow: 1000 }],
    chat: vi.fn().mockResolvedValue({
      content,
      modelUsed: "m",
      providerUsed: "anthropic_api",
      tokensInput: 100,
      tokensOutput: 200,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("reviewerRunner", () => {
  it("generates narrative commentary for bucket stats", async () => {
    const provider = makeProvider("Strong week. Bucket 0.40-0.45 stood out at 71% win rate.");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createReviewerRunner({ registry });
    const narrative = await runner.generateCommentary({
      period: "weekly",
      totalPnl7d: 127.50,
      bucketStats: [
        { price_bucket: 0.40, trade_count: 7, win_count: 5, win_rate: 0.714, total_pnl_net_usdc: 56.20 },
        { price_bucket: 0.50, trade_count: 4, win_count: 2, win_rate: 0.5, total_pnl_net_usdc: 15.80 },
      ],
      killSwitches: [],
    });
    expect(narrative).toContain("Strong week");
  });

  it("returns empty string if no provider assigned", async () => {
    const registry = { getProviderForAgent: () => null } as any;
    const runner = createReviewerRunner({ registry });
    const narrative = await runner.generateCommentary({
      period: "daily",
      totalPnl7d: 0,
      bucketStats: [],
      killSwitches: [],
    });
    expect(narrative).toBe("");
  });
});
