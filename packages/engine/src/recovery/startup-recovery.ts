import type { SignalLogRepo } from "../db/signal-log-repo.js";
import type { PortfolioStateRepo, PortfolioState } from "../db/portfolio-state-repo.js";

export interface StartupRecoveryDeps {
  signalRepo: SignalLogRepo;
  portfolioRepo: PortfolioStateRepo;
  nowMs: number;
  logger: { info: (m: string) => void; warn: (m: string) => void; error: (m: string) => void };
}

export interface RecoveryReport {
  openPositionCount: number;
  dailyHaltReset: boolean;
  weeklyHaltReset: boolean;
}

export function performStartupRecovery(deps: StartupRecoveryDeps): RecoveryReport {
  const open = deps.signalRepo.listOpen();
  deps.logger.info(`[recovery] ${open.length} open positions loaded from DB`);

  const state = deps.portfolioRepo.read();
  const patch: Partial<PortfolioState> = {};
  let dailyReset = false;
  let weeklyReset = false;

  // On any startup, conservatively clear halts and re-anchor start-of-day /
  // start-of-week equity to current equity. The user restarting the process is
  // an intentional recovery signal.
  if (state.daily_halt_triggered) {
    patch.daily_halt_triggered = false;
    patch.day_start_equity = state.current_equity;
    dailyReset = true;
  }
  if (state.weekly_halt_triggered) {
    patch.weekly_halt_triggered = false;
    patch.week_start_equity = state.current_equity;
    weeklyReset = true;
  }
  if (Object.keys(patch).length > 0) deps.portfolioRepo.update(patch);

  return {
    openPositionCount: open.length,
    dailyHaltReset: dailyReset,
    weeklyHaltReset: weeklyReset,
  };
}
