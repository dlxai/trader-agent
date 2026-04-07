import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createOpenAICompatProvider,
  type OpenAICompatConfig,
} from "../../src/adapters/openai-compat.js";

const baseConfig: OpenAICompatConfig = {
  providerId: "deepseek",
  displayName: "DeepSeek",
  apiKey: "sk-test-1234",
  baseUrl: "https://api.deepseek.com/v1",
  defaultModels: [
    { id: "deepseek-chat", contextWindow: 128000 },
    { id: "deepseek-reasoner", contextWindow: 128000 },
  ],
};

describe("openai-compat adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects successfully when base URL is reachable", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          data: [
            { id: "deepseek-chat" },
            { id: "deepseek-reasoner" },
          ],
        }),
        { status: 200 }
      )
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels()).toHaveLength(2);
  });

  it("falls back to defaultModels if /models endpoint fails", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("Not Found", { status: 404 }));
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toContain("deepseek-chat");
  });

  it("sends Authorization header on chat", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [{ id: "deepseek-chat" }] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          choices: [
            {
              message: { role: "assistant", content: "Hello there!" },
              finish_reason: "stop",
            },
          ],
          usage: { prompt_tokens: 5, completion_tokens: 3 },
          model: "deepseek-chat",
        }),
        { status: 200 }
      )
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "deepseek-chat",
    });
    expect(resp.content).toBe("Hello there!");
    expect(resp.tokensInput).toBe(5);
    expect(resp.tokensOutput).toBe(3);
    expect(resp.providerUsed).toBe("deepseek");
    const lastCall = fetchSpy.mock.calls.at(-1);
    expect(lastCall?.[1]?.headers).toMatchObject({ Authorization: "Bearer sk-test-1234" });
  });

  it("throws ProviderError on HTTP 401", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { message: "Invalid API key" } }), {
        status: 401,
      })
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    await expect(
      provider.chat({ messages: [{ role: "user", content: "x" }], model: "deepseek-chat" })
    ).rejects.toThrow(/401/);
  });
});
