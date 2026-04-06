import type { TraderConfig } from "../config/schema.js";
import type { PortfolioStateRepo, PortfolioState } from "../db/portfolio-state-repo.js";

export interface CircuitBreakerDeps {
  config: TraderConfig;
  portfolioRepo: PortfolioStateRepo;
}

export interface CircuitBreaker {
  evaluate(): void;
  canOpenNewPosition(): boolean;
  isEmergencyStop(): boolean;
  resetDaily(newDayStartEquity: number): void;
  resetWeekly(newWeekStartEquity: number): void;
}

export function createCircuitBreaker(deps: CircuitBreakerDeps): CircuitBreaker {
  const { config, portfolioRepo } = deps;

  function evaluate(): void {
    const state = portfolioRepo.read();
    const patch: Partial<PortfolioState> = {};

    if (state.day_start_equity > 0) {
      const dailyDd = (state.day_start_equity - state.current_equity) / state.day_start_equity;
      if (dailyDd >= config.dailyLossHaltPct && !state.daily_halt_triggered) {
        patch.daily_halt_triggered = true;
      }
    }

    if (state.week_start_equity > 0) {
      const weeklyDd = (state.week_start_equity - state.current_equity) / state.week_start_equity;
      if (weeklyDd >= config.weeklyLossHaltPct && !state.weekly_halt_triggered) {
        patch.weekly_halt_triggered = true;
      }
    }

    if (state.current_equity > state.peak_equity) {
      patch.peak_equity = state.current_equity;
    }

    if (state.peak_equity > 0) {
      patch.current_drawdown = Math.max(
        0,
        (state.peak_equity - state.current_equity) / state.peak_equity
      );
    }

    if (Object.keys(patch).length > 0) portfolioRepo.update(patch);
  }

  function canOpenNewPosition(): boolean {
    const state = portfolioRepo.read();
    if (state.daily_halt_triggered) return false;
    if (state.weekly_halt_triggered) return false;
    if (isEmergencyStop()) return false;
    return true;
  }

  function isEmergencyStop(): boolean {
    const state = portfolioRepo.read();
    if (state.peak_equity <= 0) return false;
    const dd = (state.peak_equity - state.current_equity) / state.peak_equity;
    return dd >= config.totalDrawdownHaltPct;
  }

  return {
    evaluate,
    canOpenNewPosition,
    isEmergencyStop,
    resetDaily(newDayStartEquity) {
      portfolioRepo.update({
        day_start_equity: newDayStartEquity,
        daily_halt_triggered: false,
      });
    },
    resetWeekly(newWeekStartEquity) {
      portfolioRepo.update({
        week_start_equity: newWeekStartEquity,
        weekly_halt_triggered: false,
      });
    },
  };
}
