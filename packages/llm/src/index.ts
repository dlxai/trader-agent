// Public exports of @pmt/llm
export type {
  AgentId,
  ProviderId,
  AuthType,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatChunk,
  ProviderModelInfo,
  ProviderConnectionState,
  LlmProvider,
} from "./types.js";
export { ProviderError } from "./types.js";

export type { ProviderRegistry, AgentAssignment } from "./registry.js";
export { createProviderRegistry } from "./registry.js";

export { resolveProviderForModel } from "./routing.js";

export { createOpenAICompatProvider } from "./adapters/openai-compat.js";
export type { OpenAICompatConfig } from "./adapters/openai-compat.js";
export { createAnthropicProvider } from "./adapters/anthropic.js";
export type { AnthropicConfig } from "./adapters/anthropic.js";
export { createGeminiProvider } from "./adapters/gemini.js";
export type { GeminiConfig } from "./adapters/gemini.js";
export { createBedrockProvider } from "./adapters/bedrock.js";
export type { BedrockConfig } from "./adapters/bedrock.js";
export { createOllamaProvider } from "./adapters/ollama.js";
export type { OllamaConfig } from "./adapters/ollama.js";

export { createAnalyzerRunner } from "./runners/analyzer-runner.js";
export type { AnalyzerRunner, ParsedVerdict, TriggerEvent } from "./runners/analyzer-runner.js";
export { createReviewerRunner } from "./runners/reviewer-runner.js";
export type { ReviewerRunner, ReviewerInput, BucketStat } from "./runners/reviewer-runner.js";
export { createRiskMgrRunner } from "./runners/risk-mgr-runner.js";
export type { RiskMgrRunner, CoordinatorBrief, CoordinatorAction, SystemStateSnapshot } from "./runners/risk-mgr-runner.js";
export { createPositionEvaluatorRunner } from "./runners/position-evaluator-runner.js";
export type { PositionEvaluatorRunner, PositionSnapshot, AccountSummary, PositionAction, PositionEvaluation } from "./runners/position-evaluator-runner.js";

export const PACKAGE_NAME = "@pmt/llm";
