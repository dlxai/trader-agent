import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createAnthropicProvider } from "../../src/adapters/anthropic.js";

describe("anthropic adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects with API key and lists default models", async () => {
    const provider = createAnthropicProvider({ mode: "api_key", apiKey: "sk-ant-test" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    const models = provider.listModels();
    expect(models.map((m) => m.id)).toContain("claude-opus-4-6");
    expect(models.map((m) => m.id)).toContain("claude-sonnet-4-6");
    expect(models.map((m) => m.id)).toContain("claude-haiku-4-5");
  });

  it("sends x-api-key header for API key mode chat", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          content: [{ type: "text", text: "Hi from Claude" }],
          model: "claude-opus-4-6",
          usage: { input_tokens: 4, output_tokens: 5 },
          stop_reason: "end_turn",
        }),
        { status: 200 }
      )
    );
    const provider = createAnthropicProvider({ mode: "api_key", apiKey: "sk-ant-key" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "claude-opus-4-6",
    });
    expect(resp.content).toBe("Hi from Claude");
    expect(resp.tokensInput).toBe(4);
    expect(resp.tokensOutput).toBe(5);
    expect(resp.providerUsed).toBe("anthropic_api");
    const headers = fetchSpy.mock.calls.at(-1)?.[1]?.headers as Record<string, string>;
    expect(headers["x-api-key"]).toBe("sk-ant-key");
    expect(headers["anthropic-version"]).toBeDefined();
  });

  it("subscription mode reads token from cli credentials provider", async () => {
    let credentialCallCount = 0;
    const provider = createAnthropicProvider({
      mode: "subscription",
      readCliToken: async () => {
        credentialCallCount++;
        return "claude-cli-token-xyz";
      },
    });
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          content: [{ type: "text", text: "via subscription" }],
          model: "claude-opus-4-6",
          usage: { input_tokens: 1, output_tokens: 1 },
          stop_reason: "end_turn",
        }),
        { status: 200 }
      )
    );
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "test" }],
      model: "claude-opus-4-6",
    });
    expect(resp.providerUsed).toBe("anthropic_subscription");
    expect(credentialCallCount).toBeGreaterThan(0);
  });

  it("throws on missing API key", () => {
    expect(() => createAnthropicProvider({ mode: "api_key", apiKey: "" })).toThrow(/api key/i);
  });
});
