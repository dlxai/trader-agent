import type { ChatChunk, ChatRequest, ChatResponse, LlmProvider, ProviderModelInfo } from "../types.js";
import { ProviderError } from "../types.js";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "anthropic.claude-opus-4-v1:0", contextWindow: 200000 },
  { id: "anthropic.claude-sonnet-4-v1:0", contextWindow: 200000 },
  { id: "meta.llama3-70b-instruct-v1:0", contextWindow: 8192 },
];

export interface BedrockConfig {
  region: string;
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
}

export function createBedrockProvider(config: BedrockConfig): LlmProvider {
  let connected = false;
  void config; // unused until full implementation

  return {
    id: "bedrock",
    authType: "aws",
    displayName: "AWS Bedrock",

    async connect() {
      connected = true;
    },
    isConnected() {
      return connected;
    },
    listModels() {
      return DEFAULT_MODELS;
    },
    async chat(_request: ChatRequest): Promise<ChatResponse> {
      throw new ProviderError(
        "bedrock",
        "Bedrock chat not yet implemented — install @aws-sdk/client-bedrock-runtime and complete in a follow-up task"
      );
    },
    async *streamChat(_request: ChatRequest): AsyncIterable<ChatChunk> {
      throw new ProviderError("bedrock", "Bedrock streamChat not yet implemented");
    },
  };
}
