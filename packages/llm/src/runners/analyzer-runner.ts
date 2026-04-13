import type { ProviderRegistry } from "../registry.js";
import { ANALYZER_SYSTEM_PROMPT } from "./personas/analyzer.js";

export interface TriggerSnapshot {
  volume_1m: number;
  net_flow_1m: number;
  unique_traders_1m: number;
  price_move_5m: number;
  liquidity: number;
  current_mid_price: number;
}

export interface TriggerEvent {
  type: "trigger";
  market_id: string;
  market_title: string;
  resolves_at: number;
  triggered_at: number;
  direction: "buy_yes" | "buy_no";
  snapshot: TriggerSnapshot;
}

export interface ParsedVerdict {
  verdict: "real_signal" | "noise" | "uncertain";
  direction: "buy_yes" | "buy_no";
  confidence: number;
  reasoning: string;
  estimated_fair_value?: number;
  edge?: number;
  suggested_stop_loss_pct?: number;
  risk_notes?: string;
}

export interface AccountContext {
  current_equity: number;
  open_position_count: number;
  total_exposure: number;
  existing_markets: string[];
}

export interface AnalyzerRunnerOptions {
  registry: ProviderRegistry;
  timeoutMs?: number;
}

export interface AnalyzerRunner {
  judge(trigger: TriggerEvent, account?: AccountContext): Promise<ParsedVerdict | null>;
}

function buildPrompt(trigger: TriggerEvent, account?: AccountContext): string {
  const ms = trigger.resolves_at - trigger.triggered_at;
  const hours = Math.floor(ms / 3600000);
  const mins = Math.floor((ms % 3600000) / 60000);
  const resolveIn = hours > 0 ? `${hours}h ${mins}m` : `${mins} minutes`;
  return `Market: "${trigger.market_title}"
Market ID: ${trigger.market_id}
Current price: ${trigger.snapshot.current_mid_price.toFixed(4)}
Resolves in: ${resolveIn}
Liquidity: $${trigger.snapshot.liquidity.toFixed(0)}

Detected flow indicators:
- Volume (1m): $${trigger.snapshot.volume_1m.toFixed(0)}
- Net flow (1m): $${trigger.snapshot.net_flow_1m.toFixed(0)} (${trigger.direction === "buy_yes" ? "toward YES" : "toward NO"})
- Unique traders (1m): ${trigger.snapshot.unique_traders_1m}
- Price move (5m): ${(trigger.snapshot.price_move_5m * 100).toFixed(2)}%

Suggested direction from flow: ${trigger.direction}
${account != null ? `
Account state:
- Current equity: $${account.current_equity.toFixed(2)}
- Open positions: ${account.open_position_count}
- Total exposure: $${account.total_exposure.toFixed(2)}${account.existing_markets.includes(trigger.market_id) ? `
WARNING: You already have an open position in this market (${trigger.market_id}). Factor this into your analysis.` : ""}` : ""}
Respond with ONLY the JSON verdict object.`;
}

function tryParseVerdict(text: string): ParsedVerdict | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (!["real_signal", "noise", "uncertain"].includes(o.verdict as string)) return null;
    if (!["buy_yes", "buy_no"].includes(o.direction as string)) return null;
    const conf = Number(o.confidence);
    if (!Number.isFinite(conf) || conf < 0 || conf > 1) return null;
    return {
      verdict: o.verdict as ParsedVerdict["verdict"],
      direction: o.direction as ParsedVerdict["direction"],
      confidence: conf,
      reasoning: typeof o.reasoning === "string" ? o.reasoning : "",
      estimated_fair_value: typeof o.estimated_fair_value === "number" ? o.estimated_fair_value : undefined,
      edge: typeof o.edge === "number" ? o.edge : undefined,
      suggested_stop_loss_pct: typeof o.suggested_stop_loss_pct === "number" ? o.suggested_stop_loss_pct : undefined,
      risk_notes: typeof o.risk_notes === "string" ? o.risk_notes : undefined,
    };
  } catch {
    return null;
  }
}

export function createAnalyzerRunner(opts: AnalyzerRunnerOptions): AnalyzerRunner {
  const timeoutMs = opts.timeoutMs ?? 30000;

  return {
    async judge(trigger: TriggerEvent, account?: AccountContext): Promise<ParsedVerdict | null> {
      const assigned = opts.registry.getProviderForAgent("analyzer");
      if (!assigned) return null;

      const prompt = buildPrompt(trigger, account);
      const chatPromise = assigned.provider.chat({
        model: assigned.modelId,
        messages: [
          { role: "system", content: ANALYZER_SYSTEM_PROMPT },
          { role: "user", content: prompt },
        ],
        temperature: 0.3,
        maxTokens: 500,
      });

      const timeoutPromise = new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), timeoutMs)
      );

      const result = await Promise.race([
        chatPromise.catch(() => null),
        timeoutPromise,
      ]);
      if (!result) return null;
      return tryParseVerdict(result.content);
    },
  };
}
