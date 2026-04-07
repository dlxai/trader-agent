import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createGeminiProvider } from "../../src/adapters/gemini.js";

describe("gemini adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("api key mode: connects and lists default models", async () => {
    const provider = createGeminiProvider({ mode: "api_key", apiKey: "AIza-test" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toContain("gemini-2.5-pro");
    expect(provider.listModels().map((m) => m.id)).toContain("gemini-2.5-flash");
  });

  it("api key mode: appends key as query param", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          candidates: [
            {
              content: { parts: [{ text: "Gemini reply" }] },
              finishReason: "STOP",
            },
          ],
          usageMetadata: { promptTokenCount: 6, candidatesTokenCount: 4 },
        }),
        { status: 200 }
      )
    );
    const provider = createGeminiProvider({ mode: "api_key", apiKey: "AIza-key-123" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "gemini-2.5-flash",
    });
    expect(resp.content).toBe("Gemini reply");
    expect(resp.tokensInput).toBe(6);
    expect(resp.tokensOutput).toBe(4);
    expect(resp.providerUsed).toBe("gemini_api");
    const url = fetchSpy.mock.calls.at(-1)?.[0] as string;
    expect(url).toContain("key=AIza-key-123");
  });

  it("oauth mode: uses Bearer token", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          candidates: [{ content: { parts: [{ text: "via oauth" }] }, finishReason: "STOP" }],
          usageMetadata: { promptTokenCount: 1, candidatesTokenCount: 1 },
        }),
        { status: 200 }
      )
    );
    const provider = createGeminiProvider({
      mode: "oauth",
      getAccessToken: async () => "ya29.test-oauth-token",
    });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "x" }],
      model: "gemini-2.5-flash",
    });
    expect(resp.providerUsed).toBe("gemini_oauth");
    const headers = fetchSpy.mock.calls.at(-1)?.[1]?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer ya29.test-oauth-token");
  });
});
