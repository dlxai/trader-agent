import type { ChatChunk, ChatRequest, ChatResponse, LlmProvider, ProviderModelInfo } from "../types.js";
import { ProviderError } from "../types.js";

export interface OllamaConfig {
  baseUrl: string;
  timeoutMs?: number;
}

interface OllamaListResponse {
  models: Array<{ name: string }>;
}

interface OllamaChatResponse {
  message: { role: string; content: string };
  model: string;
  prompt_eval_count?: number;
  eval_count?: number;
  done_reason?: string;
}

export function createOllamaProvider(config: OllamaConfig): LlmProvider {
  let connected = false;
  let models: ProviderModelInfo[] = [];

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 60000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  return {
    id: "ollama",
    authType: "api_key",
    displayName: "Ollama (local)",

    async connect() {
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/tags`, { method: "GET" });
      if (!resp.ok) {
        throw new ProviderError("ollama", `failed to reach Ollama at ${config.baseUrl}: HTTP ${resp.status}`);
      }
      const json = (await resp.json()) as OllamaListResponse;
      models = json.models.map((m) => ({ id: m.name, contextWindow: 8192 }));
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      return models;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      if (!connected) throw new ProviderError("ollama", "not connected");
      const options: Record<string, unknown> = {
        temperature: request.temperature ?? 0.7,
      };
      if (request.maxTokens !== undefined) options.num_predict = request.maxTokens;
      const body = {
        model: request.model,
        messages: request.messages,
        stream: false,
        options,
      };
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError("ollama", `HTTP ${resp.status}: ${text}`);
      }
      const json = (await resp.json()) as OllamaChatResponse;
      return {
        content: json.message.content,
        modelUsed: json.model,
        providerUsed: "ollama",
        tokensInput: json.prompt_eval_count ?? 0,
        tokensOutput: json.eval_count ?? 0,
        finishReason: json.done_reason === "stop" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      if (!connected) throw new ProviderError("ollama", "not connected");
      const body = {
        model: request.model,
        messages: request.messages,
        stream: true,
      };
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError("ollama", `HTTP ${resp.status}`);
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
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line);
            const delta = obj.message?.content ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.done) {
              tokensIn = obj.prompt_eval_count ?? 0;
              tokensOut = obj.eval_count ?? 0;
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
          providerUsed: "ollama",
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}
