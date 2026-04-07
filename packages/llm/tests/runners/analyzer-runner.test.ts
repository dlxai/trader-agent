import { describe, it, expect, vi } from "vitest";
import { createAnalyzerRunner } from "../../src/runners/analyzer-runner.js";
import type { LlmProvider } from "../../src/types.js";

function makeProvider(replyContent: string): LlmProvider {
  return {
    id: "anthropic_api" as any,
    authType: "api_key",
    displayName: "Test",
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => [{ id: "test-model", contextWindow: 100000 }],
    chat: vi.fn().mockResolvedValue({
      content: replyContent,
      modelUsed: "test-model",
      providerUsed: "anthropic_api",
      tokensInput: 100,
      tokensOutput: 50,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("analyzerRunner", () => {
  const sampleTrigger = {
    type: "trigger" as const,
    market_id: "m1",
    market_title: "Will it rain?",
    resolves_at: Date.now() + 7_200_000,
    triggered_at: Date.now(),
    direction: "buy_yes" as const,
    snapshot: {
      volume_1m: 3500,
      net_flow_1m: 3200,
      unique_traders_1m: 4,
      price_move_5m: 0.04,
      liquidity: 6000,
      current_mid_price: 0.55,
    },
  };

  it("parses a real_signal verdict from LLM JSON response", async () => {
    const provider = makeProvider(
      JSON.stringify({
        verdict: "real_signal",
        direction: "buy_yes",
        confidence: 0.8,
        reasoning: "Strong flow",
      })
    );
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).not.toBeNull();
    expect(result?.verdict).toBe("real_signal");
    expect(result?.confidence).toBe(0.8);
  });

  it("returns null if no provider assigned", async () => {
    const registry = { getProviderForAgent: () => null } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });

  it("returns null on LLM timeout", async () => {
    const provider = {
      id: "anthropic_api" as any,
      authType: "api_key",
      displayName: "Test",
      connect: vi.fn(),
      isConnected: () => true,
      listModels: () => [{ id: "test-model", contextWindow: 100000 }],
      chat: vi.fn().mockImplementation(() => new Promise(() => {})), // never resolves
      streamChat: vi.fn() as any,
    };
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry, timeoutMs: 50 });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });

  it("returns null on unparseable LLM output", async () => {
    const provider = makeProvider("This is not JSON");
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });
});
