import type { TraderConfig } from "../config/schema.js";
import type { SignalLogRow, ExitReason } from "../db/types.js";
import type { DrawdownGuard } from "./drawdown-guard.js";

export interface ExitContext {
  currentPrice: number;
  nowMs: number;
}

export interface ExitDecision {
  exit: boolean;
  reason?: ExitReason;
}

export function evaluateExit(
  position: SignalLogRow,
  ctx: ExitContext,
  cfg: TraderConfig,
  drawdownGuard?: DrawdownGuard
): ExitDecision {
  const secToResolve = Math.floor((position.resolves_at - ctx.nowMs) / 1000);
  if (secToResolve <= cfg.expirySafetyBufferSec) {
    return { exit: true, reason: "E" };
  }

  const isLateStage = secToResolve <= cfg.lateStageThresholdSec;
  const stopLossPct = isLateStage ? cfg.stopLossPctLateStage : cfg.stopLossPctNormal;

  const rawDelta = (ctx.currentPrice - position.entry_price) / position.entry_price;
  const profitDelta = position.direction === "buy_yes" ? rawDelta : -rawDelta;

  if (profitDelta <= -(stopLossPct - 1e-9)) {
    return { exit: true, reason: "A_SL" };
  }
  if (profitDelta >= cfg.takeProfitPct) {
    return { exit: true, reason: "A_TP" };
  }

  if (drawdownGuard) {
    drawdownGuard.onPriceTick(position.signal_id, profitDelta);
    if (drawdownGuard.shouldExit(position.signal_id, profitDelta)) {
      return { exit: true, reason: "DRAWDOWN_GUARD" };
    }
  }

  const holdingSec = Math.floor((ctx.nowMs - position.triggered_at) / 1000);
  if (holdingSec >= cfg.maxHoldingSec) {
    return { exit: true, reason: "C" };
  }

  return { exit: false };
}
