import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createOllamaProvider } from "../../src/adapters/ollama.js";

describe("ollama adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects to localhost and discovers models", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          models: [
            { name: "qwen2.5:32b" },
            { name: "deepseek-r1:14b" },
          ],
        }),
        { status: 200 }
      )
    );
    const provider = createOllamaProvider({ baseUrl: "http://localhost:11434" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toEqual(["qwen2.5:32b", "deepseek-r1:14b"]);
  });

  it("chat returns content", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ models: [{ name: "qwen2.5:32b" }] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          message: { role: "assistant", content: "Local model says hi" },
          model: "qwen2.5:32b",
          prompt_eval_count: 3,
          eval_count: 8,
          done_reason: "stop",
        }),
        { status: 200 }
      )
    );
    const provider = createOllamaProvider({ baseUrl: "http://localhost:11434" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "qwen2.5:32b",
    });
    expect(resp.content).toBe("Local model says hi");
    expect(resp.tokensInput).toBe(3);
    expect(resp.tokensOutput).toBe(8);
  });
});
