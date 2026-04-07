import { describe, it, expect } from "vitest";
import type {
  AgentId,
  ProviderId,
  AuthType,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatChunk,
  LlmProvider,
  ProviderModelInfo,
} from "../src/types.js";

describe("@pmt/llm types", () => {
  it("AgentId enum literals", () => {
    const a: AgentId = "analyzer";
    const r: AgentId = "reviewer";
    const m: AgentId = "risk_manager";
    expect([a, r, m]).toEqual(["analyzer", "reviewer", "risk_manager"]);
  });

  it("ChatMessage shape", () => {
    const msg: ChatMessage = {
      role: "user",
      content: "hi",
    };
    expect(msg.role).toBe("user");
  });

  it("ChatResponse shape", () => {
    const resp: ChatResponse = {
      content: "hello back",
      modelUsed: "claude-opus-4-6",
      providerUsed: "anthropic_api",
      tokensInput: 10,
      tokensOutput: 5,
      finishReason: "stop",
    };
    expect(resp.tokensInput).toBe(10);
  });
});
