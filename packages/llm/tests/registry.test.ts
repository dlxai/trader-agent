import { describe, it, expect, beforeEach, vi } from "vitest";
import { createProviderRegistry } from "../src/registry.js";
import type { LlmProvider } from "../src/types.js";

function makeFakeProvider(id: string): LlmProvider {
  return {
    id: id as any,
    authType: "api_key",
    displayName: id,
    connect: vi.fn().mockResolvedValue(undefined),
    isConnected: () => true,
    listModels: () => [{ id: "model-a", contextWindow: 1000 }],
    chat: vi.fn(),
    streamChat: vi.fn() as any,
  };
}

describe("providerRegistry", () => {
  let registry: ReturnType<typeof createProviderRegistry>;

  beforeEach(() => {
    registry = createProviderRegistry();
  });

  it("registers and retrieves a provider", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    expect(registry.get("anthropic_api")).toBe(provider);
  });

  it("listConnected returns only connected providers", () => {
    const a = makeFakeProvider("anthropic_api");
    const b = { ...makeFakeProvider("openai"), isConnected: () => false };
    registry.register(a);
    registry.register(b as any);
    expect(registry.listConnected()).toHaveLength(1);
    expect(registry.listConnected()[0]?.id).toBe("anthropic_api");
  });

  it("assignAgentModel sets a provider+model for an agent", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    registry.assignAgentModel("analyzer", "anthropic_api", "model-a");
    const assignment = registry.getAgentAssignment("analyzer");
    expect(assignment?.providerId).toBe("anthropic_api");
    expect(assignment?.modelId).toBe("model-a");
  });

  it("getProviderForAgent returns the registered provider", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    registry.assignAgentModel("analyzer", "anthropic_api", "model-a");
    const result = registry.getProviderForAgent("analyzer");
    expect(result?.provider.id).toBe("anthropic_api");
    expect(result?.modelId).toBe("model-a");
  });

  it("getProviderForAgent returns null if no assignment", () => {
    expect(registry.getProviderForAgent("analyzer")).toBeNull();
  });
});
