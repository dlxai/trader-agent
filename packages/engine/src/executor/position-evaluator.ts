export interface PositionAction {
  signal_id: string;
  action: "close" | "hold" | "adjust_sl_tp";
  new_stop_loss_pct?: number;
  new_take_profit_pct?: number;
  reasoning: string;
}

export interface PositionEvaluatorLoopConfig {
  intervalSec: number;
  getOpenPositions: () => Array<{ signal_id: string; market_id: string; entry_price: number; size_usdc: number; [key: string]: any }>;
  evaluate: (account: any, positions: any[]) => Promise<{ positions: PositionAction[] } | null>;
  onAction: (action: PositionAction) => void;
}

export interface PositionEvaluatorLoop {
  start(): void;
  stop(): void;
  triggerNow(): Promise<void>;
}

export function createPositionEvaluatorLoop(config: PositionEvaluatorLoopConfig): PositionEvaluatorLoop {
  let timer: ReturnType<typeof setInterval> | null = null;

  async function runOnce(): Promise<void> {
    const openPositions = config.getOpenPositions();
    if (openPositions.length === 0) return;

    const account = {
      current_equity: 0,
      total_exposure: openPositions.reduce((sum, p) => sum + (p.size_usdc ?? 0), 0),
      open_position_count: openPositions.length,
    };

    const evaluation = await config.evaluate(account, openPositions);
    if (!evaluation) return;

    for (const action of evaluation.positions) {
      if (action.action !== "hold") {
        config.onAction(action);
      }
    }
  }

  return {
    start() {
      if (timer) return;
      timer = setInterval(() => { runOnce().catch(() => {}); }, config.intervalSec * 1000);
    },
    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    },
    async triggerNow() {
      await runOnce();
    },
  };
}
