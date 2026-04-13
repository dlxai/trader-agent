export type AgentId = "analyzer" | "reviewer" | "risk_manager" | "position_evaluator";

export type ProviderId =
  // OpenAI-compatible API key providers
  | "anthropic_api"
  | "openai"
  | "deepseek"
  | "zhipu"
  | "moonshot"
  | "qwen"
  | "groq"
  | "mistral"
  | "xai"
  | "openrouter"
  | "minimax"
  | "venice"
  | "xiaomi_mimo"
  | "volcengine"
  | "nvidia_nim"
  // Subscription / Coding plans
  | "anthropic_subscription"
  | "gemini_oauth"
  | "zhipu_coding"
  | "qwen_coding"
  | "kimi_code"
  | "minimax_coding"
  | "volcengine_coding"
  | "gemini_api"
  // AWS
  | "bedrock"
  // Local
  | "ollama";

export type AuthType = "api_key" | "oauth" | "cli_credential" | "aws";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  model: string;
  maxTokens?: number;
  temperature?: number;
  stop?: string[];
  /** Stream tokens as they arrive (caller registers a callback). */
  stream?: boolean;
}

export interface ChatResponse {
  content: string;
  modelUsed: string;
  providerUsed: ProviderId;
  tokensInput: number;
  tokensOutput: number;
  finishReason: "stop" | "length" | "content_filter" | "error";
}

export interface ChatChunk {
  delta: string;
  done: boolean;
  final?: ChatResponse;
}

export interface ProviderModelInfo {
  id: string;
  contextWindow: number;
  inputCostPer1k?: number;
  outputCostPer1k?: number;
}

export interface ProviderConnectionState {
  providerId: ProviderId;
  isConnected: boolean;
  lastError?: string;
  modelsAvailable: ProviderModelInfo[];
  quotaUsed?: number;
  quotaLimit?: number;
  quotaResetsAt?: number;
}

export interface LlmProvider {
  readonly id: ProviderId;
  readonly authType: AuthType;
  readonly displayName: string;

  /** Test connection and refresh model list. */
  connect(): Promise<void>;

  /** Returns false if not connected. */
  isConnected(): boolean;

  /** Returns models the provider currently exposes (after connect()). */
  listModels(): ProviderModelInfo[];

  /** Synchronous chat — waits for the full response. */
  chat(request: ChatRequest): Promise<ChatResponse>;

  /** Streaming chat — yields chunks as the LLM generates them. */
  streamChat(request: ChatRequest): AsyncIterable<ChatChunk>;
}

export class ProviderError extends Error {
  constructor(
    public readonly providerId: ProviderId,
    message: string,
    public readonly cause?: unknown
  ) {
    super(`[${providerId}] ${message}`);
    this.name = "ProviderError";
  }
}
