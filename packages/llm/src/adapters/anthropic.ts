import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

const ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1";
const ANTHROPIC_VERSION = "2023-06-01";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "claude-opus-4-6", contextWindow: 200000, inputCostPer1k: 0.015, outputCostPer1k: 0.075 },
  { id: "claude-sonnet-4-6", contextWindow: 200000, inputCostPer1k: 0.003, outputCostPer1k: 0.015 },
  { id: "claude-haiku-4-5", contextWindow: 200000, inputCostPer1k: 0.0008, outputCostPer1k: 0.004 },
];

export type AnthropicConfig =
  | {
      mode: "api_key";
      apiKey: string;
      timeoutMs?: number;
      /** Override base URL for Anthropic-compatible third-party endpoints. */
      baseUrl?: string;
      /** Override provider ID when using a third-party endpoint. */
      overrideId?: ProviderId;
      /** Override display name. */
      displayName?: string;
      /** Override available models. */
      models?: ProviderModelInfo[];
    }
  | {
      mode: "subscription";
      readCliToken: () => Promise<string>;
      timeoutMs?: number;
    };

interface AnthropicChatResponse {
  content: Array<{ type: string; text: string }>;
  model: string;
  usage: { input_tokens: number; output_tokens: number };
  stop_reason: string;
}

export function createAnthropicProvider(config: AnthropicConfig): LlmProvider {
  if (config.mode === "api_key" && !config.apiKey) {
    throw new Error("anthropic adapter: api key is required");
  }
  let connected = false;
  let dynamicModels: ProviderModelInfo[] | null = null;

  async function getAuthHeaders(): Promise<Record<string, string>> {
    const base: Record<string, string> = {
      "anthropic-version": ANTHROPIC_VERSION,
      "Content-Type": "application/json",
    };
    if (config.mode === "api_key") {
      base["x-api-key"] = config.apiKey;
    } else {
      const token = await config.readCliToken();
      base["Authorization"] = `Bearer ${token}`;
    }
    return base;
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

  const baseUrl =
    config.mode === "api_key" && config.baseUrl
      ? config.baseUrl.replace(/\/$/, "")
      : ANTHROPIC_BASE_URL;
  const providerId =
    config.mode === "api_key"
      ? (config.overrideId ?? "anthropic_api")
      : "anthropic_subscription";

  return {
    id: providerId,
    authType: config.mode === "api_key" ? "api_key" : "cli_credential",
    displayName:
      config.mode === "api_key"
        ? (config.displayName ?? "Anthropic API")
        : "Anthropic Subscription",

    async connect() {
      // Custom endpoints (e.g. Volcengine) may expose a /models endpoint;
      // standard Anthropic does not, so we only try when baseUrl is overridden.
      // Skip if user provided models (including empty array to opt-out of auto-fetch).
      const skipFetch = config.mode === "api_key" && config.models !== undefined;
      if (config.mode === "api_key" && config.baseUrl && !skipFetch) {
        const headers = await getAuthHeaders();
        const resp = await fetchWithTimeout(`${baseUrl}/models`, {
          method: "GET",
          headers,
        });
        if (!resp.ok) {
          const text = await resp.text().catch(() => "");
          throw new ProviderError(providerId, `Failed to fetch models: HTTP ${resp.status}: ${text.slice(0, 200)}`);
        }
        const json = (await resp.json()) as { data: Array<{ id: string; context_window?: number }> };
        if (!Array.isArray(json.data) || json.data.length === 0) {
          throw new ProviderError(providerId, "No models returned from /models endpoint");
        }
        dynamicModels = json.data.map((m) => ({
          id: m.id,
          contextWindow: m.context_window ?? 0,
        }));
      }
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      if (dynamicModels) return dynamicModels;
      if (config.mode === "api_key" && config.models?.length) return config.models;
      return DEFAULT_MODELS;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      const headers = await getAuthHeaders();
      const systemMessages = request.messages.filter((m) => m.role === "system");
      const otherMessages = request.messages.filter((m) => m.role !== "system");
      // Build body with conditional spread for strict optional types
      const body: Record<string, unknown> = {
        model: request.model,
        max_tokens: request.maxTokens ?? 4096,
        temperature: request.temperature ?? 0.7,
        messages: otherMessages.map((m) => ({ role: m.role, content: m.content })),
      };
      const sysJoined = systemMessages.map((m) => m.content).join("\n\n");
      if (sysJoined) body.system = sysJoined;
      if (request.stop !== undefined) body.stop_sequences = request.stop;

      const resp = await fetchWithTimeout(`${baseUrl}/messages`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(providerId, `HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const json = (await resp.json()) as AnthropicChatResponse;
      const text = json.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("");
      return {
        content: text,
        modelUsed: json.model,
        providerUsed: providerId,
        tokensInput: json.usage.input_tokens,
        tokensOutput: json.usage.output_tokens,
        finishReason: json.stop_reason === "end_turn" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      const headers = await getAuthHeaders();
      const systemMessages = request.messages.filter((m) => m.role === "system");
      const otherMessages = request.messages.filter((m) => m.role !== "system");
      const body: Record<string, unknown> = {
        model: request.model,
        max_tokens: request.maxTokens ?? 4096,
        messages: otherMessages.map((m) => ({ role: m.role, content: m.content })),
        stream: true,
      };
      const sysJoined = systemMessages.map((m) => m.content).join("\n\n");
      if (sysJoined) body.system = sysJoined;

      const resp = await fetchWithTimeout(`${baseUrl}/messages`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
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
          const payload = line.slice(6).trim();
          if (!payload) continue;
          try {
            const obj = JSON.parse(payload);
            if (obj.type === "content_block_delta" && obj.delta?.text) {
              fullContent += obj.delta.text;
              yield { delta: obj.delta.text, done: false };
            }
            if (obj.type === "message_delta" && obj.usage) {
              tokensOut = obj.usage.output_tokens ?? tokensOut;
            }
            if (obj.type === "message_start" && obj.message?.usage) {
              tokensIn = obj.message.usage.input_tokens ?? 0;
            }
          } catch {
            // ignore malformed events
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
