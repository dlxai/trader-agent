import { describe, it, expect, vi } from "vitest";
import { createAnalyzerClient } from "../../src/analyzer/analyzer-client.js";
import { LlmTimeoutError } from "../../src/util/errors.js";

describe("analyzerClient", () => {
  it("returns parsed verdict on success", async () => {
    const invoker = vi.fn().mockResolvedValue(
      JSON.stringify({
        verdict: "real_signal",
        direction: "buy_yes",
        confidence: 0.8,
        reasoning: "test",
      })
    );
    const client = createAnalyzerClient({
      agentId: "polymarket-analyzer",
      timeoutMs: 5_000,
      invoker,
    });
    const result = await client.judge("some prompt");
    expect(result.verdict).toBe("real_signal");
    expect(invoker).toHaveBeenCalledWith("polymarket-analyzer", "some prompt");
  });

  it("throws LlmTimeoutError when invoker exceeds timeout", async () => {
    const invoker = vi.fn().mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve("{}"), 200))
    );
    const client = createAnalyzerClient({
      agentId: "polymarket-analyzer",
      timeoutMs: 50,
      invoker,
    });
    await expect(client.judge("prompt")).rejects.toThrow(LlmTimeoutError);
  });
});
