import { describe, it, expect, vi } from "vitest";
import { createRiskMgrRunner } from "../../src/runners/risk-mgr-runner.js";
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
      tokensOutput: 50,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("riskMgrRunner reactive mode", () => {
  it("answers user question with system state context", async () => {
    const provider = makeProvider("Currently safe. Daily DD: -0.8%, well under -2.0% halt.");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const reply = await runner.answerQuestion({
      question: "Are we close to any halts?",
      systemState: {
        portfolioState: {
          current_equity: 9920,
          day_start_equity: 10000,
          daily_halt_triggered: false,
        },
        recentTrades: [],
        openPositionCount: 3,
      },
    });
    expect(reply).toContain("safe");
  });
});

describe("riskMgrRunner proactive mode", () => {
  it("returns parsed Coordinator brief JSON", async () => {
    const provider = makeProvider(
      JSON.stringify({
        summary: "Stable hour. 7 triggers, 2 entered.",
        alerts: [{ severity: "info", text: "BTC market activity elevated" }],
        suggestions: ["Consider tightening unique_traders_1m to 4"],
      })
    );
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const brief = await runner.generateBrief({
      windowMs: 3600000,
      systemState: {
        portfolioState: {
          current_equity: 10100,
          day_start_equity: 10000,
          daily_halt_triggered: false,
        },
        recentTrades: [],
        openPositionCount: 2,
      },
    });
    expect(brief).not.toBeNull();
    expect(brief?.summary).toContain("Stable");
    expect(brief?.alerts).toHaveLength(1);
    expect(brief?.suggestions).toHaveLength(1);
  });

  it("returns null if Coordinator output is unparseable", async () => {
    const provider = makeProvider("not json");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const brief = await runner.generateBrief({
      windowMs: 3600000,
      systemState: {
        portfolioState: { current_equity: 10000, day_start_equity: 10000, daily_halt_triggered: false },
        recentTrades: [],
        openPositionCount: 0,
      },
    });
    expect(brief).toBeNull();
  });
});
