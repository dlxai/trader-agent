import type { ProviderRegistry } from "../registry.js";
import { POSITION_EVALUATOR_SYSTEM_PROMPT } from "./personas/position-evaluator.js";

export interface PositionSnapshot {
  signal_id: string;
  market_title: string;
  resolves_at: number;
  direction: "buy_yes" | "buy_no";
  entry_price: number;
  current_price: number;
  pnl_pct: number;
  peak_pnl_pct: number;
  holding_duration_sec: number;
  llm_reasoning: string;
  snapshot_net_flow_1m: number;
  snapshot_volume_1m: number;
}

export interface AccountSummary {
  current_equity: number;
  total_exposure: number;
  open_position_count: number;
}

export interface PositionAction {
  signal_id: string;
  action: "close" | "hold" | "adjust_sl_tp";
  new_stop_loss_pct?: number;
  new_take_profit_pct?: number;
  reasoning: string;
}

export interface PositionEvaluation {
  positions: PositionAction[];
}

const VALID_ACTIONS = new Set(["close", "hold", "adjust_sl_tp"]);

export function parsePositionEvaluation(text: string): PositionEvaluation | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || !Array.isArray(obj.positions)) return null;
    const positions: PositionAction[] = [];
    for (const p of obj.positions) {
      if (!p || typeof p.signal_id !== "string" || !VALID_ACTIONS.has(p.action)) continue;
      positions.push({
        signal_id: p.signal_id,
        action: p.action,
        new_stop_loss_pct: typeof p.new_stop_loss_pct === "number" ? p.new_stop_loss_pct : undefined,
        new_take_profit_pct: typeof p.new_take_profit_pct === "number" ? p.new_take_profit_pct : undefined,
        reasoning: typeof p.reasoning === "string" ? p.reasoning : "",
      });
    }
    return { positions };
  } catch {
    return null;
  }
}

function buildPrompt(account: AccountSummary, positions: PositionSnapshot[]): string {
  const lines: string[] = [];
  lines.push(`Account: equity=$${account.current_equity.toFixed(2)} exposure=$${account.total_exposure.toFixed(2)} open=${account.open_position_count}`);
  lines.push("");
  for (const p of positions) {
    const msToResolve = p.resolves_at - Date.now();
    const hoursLeft = Math.max(0, msToResolve / 3600000).toFixed(1);
    lines.push(`Position [${p.signal_id}]:`);
    lines.push(`  Market: "${p.market_title}"`);
    lines.push(`  Direction: ${p.direction}, Entry: ${p.entry_price.toFixed(4)}, Current: ${p.current_price.toFixed(4)}`);
    lines.push(`  PnL: ${(p.pnl_pct * 100).toFixed(2)}%, Peak PnL: ${(p.peak_pnl_pct * 100).toFixed(2)}%`);
    lines.push(`  Holding: ${Math.floor(p.holding_duration_sec / 60)} min, Resolves in: ${hoursLeft}h`);
    lines.push(`  Entry reasoning: "${p.llm_reasoning}"`);
    lines.push(`  Current flow: volume_1m=$${p.snapshot_volume_1m.toFixed(0)} net_flow=$${p.snapshot_net_flow_1m.toFixed(0)}`);
    lines.push("");
  }
  lines.push("Evaluate each position. Respond with ONLY the JSON.");
  return lines.join("\n");
}

export interface PositionEvaluatorRunner {
  evaluate(account: AccountSummary, positions: PositionSnapshot[]): Promise<PositionEvaluation | null>;
}

export function createPositionEvaluatorRunner(opts: { registry: ProviderRegistry }): PositionEvaluatorRunner {
  return {
    async evaluate(account, positions) {
      if (positions.length === 0) return { positions: [] };
      const assigned = opts.registry.getProviderForAgent("position_evaluator");
      if (!assigned) return null;
      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: POSITION_EVALUATOR_SYSTEM_PROMPT },
            { role: "user", content: buildPrompt(account, positions) },
          ],
          temperature: 0.3,
          maxTokens: 800,
        });
        return parsePositionEvaluation(resp.content);
      } catch {
        return null;
      }
    },
  };
}
