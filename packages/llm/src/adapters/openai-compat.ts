import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderId,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

export interface OpenAICompatConfig {
  providerId: ProviderId;
  displayName: string;
  apiKey: string;
  baseUrl: string;
  defaultModels: ProviderModelInfo[];
  /** Optional extra headers (e.g., OpenRouter wants HTTP-Referer). */
  extraHeaders?: Record<string, string>;
  /** Override request timeout in ms (default 30000). */
  timeoutMs?: number;
  /** When true, throw on /models fetch failure instead of falling back to defaultModels. */
  strictModels?: boolean;
}

interface OpenAIModelsResponse {
  data: Array<{ id: string }>;
}

interface OpenAIChatResponse {
  choices: Array<{
    message: { role: string; content: string };
    finish_reason: string;
  }>;
  usage?: { prompt_tokens: number; completion_tokens: number };
  model?: string;
}

export function createOpenAICompatProvider(config: OpenAICompatConfig): LlmProvider {
  let connected = false;
  let models: ProviderModelInfo[] = [];

  function buildHeaders(): Record<string, string> {
    return {
      Authorization: `Bearer ${config.apiKey}`,
      "Content-Type": "application/json",
      ...(config.extraHeaders ?? {}),
    };
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

  return {
    id: config.providerId,
    authType: "api_key",
    displayName: config.displayName,

    async connect() {
      const resp = await fetchWithTimeout(`${config.baseUrl}/models`, {
        method: "GET",
        headers: buildHeaders(),
      });
      if (resp.ok) {
        const json = (await resp.json()) as OpenAIModelsResponse;
        models = json.data.length > 0
          ? json.data.map((m) => ({ id: m.id, contextWindow: 0 }))
          : config.defaultModels;
      } else if (config.strictModels) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(config.providerId, `Failed to fetch models: HTTP ${resp.status}: ${text.slice(0, 200)}`);
      } else {
        models = config.defaultModels;
      }
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      return models.length > 0 ? models : config.defaultModels;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      if (!connected) {
        throw new ProviderError(config.providerId, "not connected — call connect() first");
      }
      const body: Record<string, unknown> = {
        model: request.model,
        messages: request.messages,
        temperature: request.temperature ?? 0.7,
        stream: false,
      };
      if (request.maxTokens !== undefined) {
        body.max_tokens = request.maxTokens;
      }
      if (request.stop !== undefined) {
        body.stop = request.stop;
      }
      let resp: Response;
      try {
        resp = await fetchWithTimeout(`${config.baseUrl}/chat/completions`, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify(body),
        });
      } catch (err) {
        throw new ProviderError(config.providerId, "network error", err);
      }
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(
          config.providerId,
          `HTTP ${resp.status}: ${text.slice(0, 200)}`
        );
      }
      const json = (await resp.json()) as OpenAIChatResponse;
      const choice = json.choices[0];
      if (!choice) {
        throw new ProviderError(config.providerId, "empty choices array");
      }
      return {
        content: choice.message.content,
        modelUsed: json.model ?? request.model,
        providerUsed: config.providerId,
        tokensInput: json.usage?.prompt_tokens ?? 0,
        tokensOutput: json.usage?.completion_tokens ?? 0,
        finishReason: mapFinishReason(choice.finish_reason),
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      if (!connected) {
        throw new ProviderError(config.providerId, "not connected — call connect() first");
      }
      const body: Record<string, unknown> = {
        model: request.model,
        messages: request.messages,
        temperature: request.temperature ?? 0.7,
        stream: true,
      };
      if (request.maxTokens !== undefined) {
        body.max_tokens = request.maxTokens;
      }
      const resp = await fetchWithTimeout(`${config.baseUrl}/chat/completions`, {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError(config.providerId, `HTTP ${resp.status}`);
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
          if (payload === "[DONE]") continue;
          try {
            const obj = JSON.parse(payload);
            const delta = obj.choices?.[0]?.delta?.content ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.usage) {
              tokensIn = obj.usage.prompt_tokens ?? 0;
              tokensOut = obj.usage.completion_tokens ?? 0;
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: config.providerId,
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}

function mapFinishReason(reason: string): ChatResponse["finishReason"] {
  switch (reason) {
    case "stop":
    case "stop_sequence":
      return "stop";
    case "length":
      return "length";
    case "content_filter":
      return "content_filter";
    default:
      return "stop";
  }
}
