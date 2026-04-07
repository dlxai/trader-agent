import type { LlmProvider } from "./types.js";

/**
 * Routing strategy: "Prefer Subscription".
 *
 * Priority:
 *   1. Subscription (cli_credential)
 *   2. OAuth (free tier)
 *   3. AWS (Bedrock)
 *   4. API key (paid per token)
 */
const PRIORITY_ORDER: Record<LlmProvider["authType"], number> = {
  cli_credential: 0,
  oauth: 1,
  aws: 2,
  api_key: 3,
};

export function resolveProviderForModel(
  modelId: string,
  providers: LlmProvider[]
): LlmProvider | null {
  const candidates = providers.filter((p) =>
    p.listModels().some((m) => m.id === modelId)
  );
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => PRIORITY_ORDER[a.authType] - PRIORITY_ORDER[b.authType]);
  return candidates[0] ?? null;
}
