import type { ProviderRegistry } from "../registry.js";
import { RISK_MANAGER_SYSTEM_PROMPT } from "./personas/risk-manager.js";

export interface SystemStateSnapshot {
  portfolioState: {
    current_equity: number;
    day_start_equity: number;
    daily_halt_triggered: boolean;
  };
  recentTrades: Array<{
    market_title: string;
    direction: string;
    pnl_net_usdc: number | null;
    exit_reason: string | null;
  }>;
  openPositionCount: number;
}

export interface CoordinatorAction {
  type: "emergency_close" | "adjust_exit" | "pause_new_entry" | "resume_entry";
  signal_id?: string;
  new_stop_loss_pct?: number;
  reason: string;
}

export interface CoordinatorBrief {
  summary: string;
  alerts: Array<{ severity: "info" | "warning" | "critical"; text: string }>;
  actions: CoordinatorAction[];
  suggestions: string[];
}

export interface RiskMgrRunner {
  answerQuestion(input: { question: string; systemState: SystemStateSnapshot }): Promise<string>;
  generateBrief(input: { windowMs: number; systemState: SystemStateSnapshot }): Promise<CoordinatorBrief | null>;
}

function formatSystemState(state: SystemStateSnapshot): string {
  const lines: string[] = [];
  lines.push(`current_equity: $${state.portfolioState.current_equity.toFixed(2)}`);
  lines.push(`day_start_equity: $${state.portfolioState.day_start_equity.toFixed(2)}`);
  const dailyDdPct = ((state.portfolioState.current_equity - state.portfolioState.day_start_equity) / state.portfolioState.day_start_equity) * 100;
  lines.push(`daily_pnl_pct: ${dailyDdPct.toFixed(2)}%`);
  lines.push(`daily_halt_triggered: ${state.portfolioState.daily_halt_triggered}`);
  lines.push(`open_position_count: ${state.openPositionCount}`);
  if (state.recentTrades.length > 0) {
    lines.push(`recent_trades:`);
    for (const t of state.recentTrades.slice(0, 5)) {
      lines.push(
        `  - ${t.market_title} | ${t.direction} | pnl=${t.pnl_net_usdc?.toFixed(2) ?? "open"} | exit=${t.exit_reason ?? "none"}`
      );
    }
  }
  return lines.join("\n");
}

export function createRiskMgrRunner(opts: { registry: ProviderRegistry }): RiskMgrRunner {
  return {
    async answerQuestion({ question, systemState }) {
      const assigned = opts.registry.getProviderForAgent("risk_manager");
      if (!assigned) return "(Risk Manager not configured. Set a model in Settings.)";
      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: RISK_MANAGER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `MODE: reactive\n\nSystem state:\n${formatSystemState(systemState)}\n\nQuestion: ${question}`,
            },
          ],
          temperature: 0.3,
          maxTokens: 500,
        });
        return resp.content;
      } catch (err) {
        return `(Error contacting Risk Manager: ${String(err).slice(0, 100)})`;
      }
    },

    async generateBrief({ windowMs, systemState }) {
      const assigned = opts.registry.getProviderForAgent("risk_manager");
      if (!assigned) return null;

      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: RISK_MANAGER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `MODE: proactive\nObservation window: ${Math.floor(windowMs / 60000)} minutes\n\nSystem state:\n${formatSystemState(systemState)}\n\nGenerate the Coordinator brief JSON.`,
            },
          ],
          temperature: 0.4,
          maxTokens: 600,
        });
        return parseBrief(resp.content);
      } catch {
        return null;
      }
    },
  };
}

function parseBrief(text: string): CoordinatorBrief | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (typeof o.summary !== "string") return null;
    const alerts = Array.isArray(o.alerts) ? (o.alerts as any[]) : [];
    const suggestions = Array.isArray(o.suggestions) ? (o.suggestions as any[]) : [];
    const VALID_ACTION_TYPES = new Set(["emergency_close", "adjust_exit", "pause_new_entry", "resume_entry"]);
    const rawActions = Array.isArray(o.actions) ? (o.actions as any[]) : [];
    const actions: CoordinatorAction[] = rawActions.filter(
      (a) => a && VALID_ACTION_TYPES.has(a.type) && typeof a.reason === "string"
    );
    return {
      summary: o.summary,
      alerts: alerts.filter((a) => a && typeof a.severity === "string" && typeof a.text === "string"),
      actions,
      suggestions: suggestions.filter((s) => typeof s === "string"),
    };
  } catch {
    return null;
  }
}
