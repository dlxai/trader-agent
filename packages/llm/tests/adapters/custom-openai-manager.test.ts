import { describe, it, expect } from "vitest";
import { CustomOpenAIManager } from "../../src/adapters/custom-openai-manager.js";

describe("CustomOpenAIManager", () => {
  it("adds a custom endpoint and generates provider ID", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({
      displayName: "My vLLM",
      baseUrl: "http://localhost:8000/v1",
      modelName: "qwen2.5-72b",
    });
    expect(config.id).toMatch(/^custom_my_vllm_/);
    expect(mgr.list()).toHaveLength(1);
  });

  it("creates an LlmProvider for a custom endpoint", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({
      displayName: "Test",
      baseUrl: "http://localhost:8000/v1",
      modelName: "test-model",
      apiKey: "sk-123",
    });
    const provider = mgr.createProvider(config.id);
    expect(provider).not.toBeNull();
    expect(provider!.displayName).toBe("Test");
  });

  it("removes a custom endpoint", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({ displayName: "X", baseUrl: "http://x/v1", modelName: "m" });
    mgr.remove(config.id);
    expect(mgr.list()).toHaveLength(0);
  });

  it("rejects duplicate display names", () => {
    const mgr = new CustomOpenAIManager();
    mgr.add({ displayName: "Same", baseUrl: "http://a/v1", modelName: "m" });
    expect(() => mgr.add({ displayName: "Same", baseUrl: "http://b/v1", modelName: "m" }))
      .toThrow("already exists");
  });

  it("returns null for unknown provider ID", () => {
    const mgr = new CustomOpenAIManager();
    expect(mgr.createProvider("nonexistent")).toBeNull();
  });

  it("loads saved endpoints", () => {
    const mgr = new CustomOpenAIManager();
    mgr.loadAll([
      { id: "custom_a_1", displayName: "A", baseUrl: "http://a/v1", modelName: "m1" },
      { id: "custom_b_2", displayName: "B", baseUrl: "http://b/v1", modelName: "m2" },
    ]);
    expect(mgr.list()).toHaveLength(2);
    expect(mgr.get("custom_a_1")?.displayName).toBe("A");
  });
});
