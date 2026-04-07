import { describe, it, expect, vi } from "vitest";
import { resolveProviderForModel } from "../src/routing.js";
import type { LlmProvider } from "../src/types.js";

function makeProvider(id: string, models: string[], authType: "api_key" | "cli_credential" | "oauth"): LlmProvider {
  return {
    id: id as any,
    authType,
    displayName: id,
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => models.map((m) => ({ id: m, contextWindow: 1000 })),
    chat: vi.fn(),
    streamChat: vi.fn() as any,
  };
}

describe("resolveProviderForModel (Prefer Subscription)", () => {
  it("prefers cli_credential subscription over api_key when both have model", () => {
    const sub = makeProvider("anthropic_subscription", ["claude-opus-4-6"], "cli_credential");
    const api = makeProvider("anthropic_api", ["claude-opus-4-6"], "api_key");
    const result = resolveProviderForModel("claude-opus-4-6", [sub, api]);
    expect(result?.id).toBe("anthropic_subscription");
  });

  it("prefers oauth (free tier) over api_key when both have model", () => {
    const oauth = makeProvider("gemini_oauth", ["gemini-2.5-flash"], "oauth");
    const api = makeProvider("gemini_api", ["gemini-2.5-flash"], "api_key");
    const result = resolveProviderForModel("gemini-2.5-flash", [oauth, api]);
    expect(result?.id).toBe("gemini_oauth");
  });

  it("falls back to api_key if no subscription available", () => {
    const api = makeProvider("openai", ["gpt-5"], "api_key");
    const result = resolveProviderForModel("gpt-5", [api]);
    expect(result?.id).toBe("openai");
  });

  it("returns null if no provider has the model", () => {
    const api = makeProvider("openai", ["gpt-5"], "api_key");
    expect(resolveProviderForModel("claude-opus-4-6", [api])).toBeNull();
  });
});
