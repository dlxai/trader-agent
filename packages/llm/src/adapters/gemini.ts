import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

const GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "gemini-2.5-pro", contextWindow: 2_000_000 },
  { id: "gemini-2.5-flash", contextWindow: 1_000_000 },
  { id: "gemini-2.5-flash-lite", contextWindow: 1_000_000 },
];

export type GeminiConfig =
  | { mode: "api_key"; apiKey: string; timeoutMs?: number }
  | { mode: "oauth"; getAccessToken: () => Promise<string>; timeoutMs?: number };

interface GeminiResponse {
  candidates: Array<{
    content: { parts: Array<{ text: string }> };
    finishReason: string;
  }>;
  usageMetadata?: { promptTokenCount: number; candidatesTokenCount: number };
}

export function createGeminiProvider(config: GeminiConfig): LlmProvider {
  let connected = false;
  const providerId = config.mode === "api_key" ? "gemini_api" : "gemini_oauth";

  async function buildUrl(model: string, action: "generateContent" | "streamGenerateContent"): Promise<string> {
    const base = `${GEMINI_BASE_URL}/models/${model}:${action}`;
    if (config.mode === "api_key") {
      return `${base}?key=${encodeURIComponent(config.apiKey)}`;
    }
    return base;
  }

  async function buildHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.mode === "oauth") {
      const token = await config.getAccessToken();
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 30000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  function buildBody(request: ChatRequest): unknown {
    const systemText = request.messages
      .filter((m) => m.role === "system")
      .map((m) => m.content)
      .join("\n\n");
    const contents = request.messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text: m.content }],
      }));
    const generationConfig: Record<string, unknown> = {
      temperature: request.temperature ?? 0.7,
    };
    if (request.maxTokens !== undefined) generationConfig.maxOutputTokens = request.maxTokens;
    if (request.stop !== undefined) generationConfig.stopSequences = request.stop;

    const body: Record<string, unknown> = { contents, generationConfig };
    if (systemText) body.systemInstruction = { parts: [{ text: systemText }] };
    return body;
  }

  return {
    id: providerId,
    authType: config.mode === "api_key" ? "api_key" : "oauth",
    displayName: config.mode === "api_key" ? "Gemini API" : "Gemini (Google OAuth)",

    async connect() {
      connected = true;
    },
    isConnected() {
      return connected;
    },
    listModels() {
      return DEFAULT_MODELS;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      const url = await buildUrl(request.model, "generateContent");
      const headers = await buildHeaders();
      const resp = await fetchWithTimeout(url, {
        method: "POST",
        headers,
        body: JSON.stringify(buildBody(request)),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(providerId, `HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const json = (await resp.json()) as GeminiResponse;
      const candidate = json.candidates[0];
      if (!candidate) {
        throw new ProviderError(providerId, "empty candidates array");
      }
      const text = candidate.content.parts.map((p) => p.text).join("");
      return {
        content: text,
        modelUsed: request.model,
        providerUsed: providerId,
        tokensInput: json.usageMetadata?.promptTokenCount ?? 0,
        tokensOutput: json.usageMetadata?.candidatesTokenCount ?? 0,
        finishReason: candidate.finishReason === "STOP" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      const url = await buildUrl(request.model, "streamGenerateContent");
      const headers = await buildHeaders();
      const resp = await fetchWithTimeout(`${url}${url.includes("?") ? "&" : "?"}alt=sse`, {
        method: "POST",
        headers,
        body: JSON.stringify(buildBody(request)),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError(providerId, `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let tokensIn = 0;
      let tokensOut = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const obj = JSON.parse(line.slice(6)) as GeminiResponse;
            const delta = obj.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.usageMetadata) {
              tokensIn = obj.usageMetadata.promptTokenCount ?? tokensIn;
              tokensOut = obj.usageMetadata.candidatesTokenCount ?? tokensOut;
            }
          } catch {
            // ignore
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: providerId,
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}
