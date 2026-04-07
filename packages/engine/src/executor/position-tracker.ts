import type { SignalLogRepo } from "../db/signal-log-repo.js";
import type { NewSignal, SignalLogRow, ExitFill } from "../db/types.js";

export interface PositionTracker {
  open(signal: NewSignal): void;
  close(signalId: string, fill: ExitFill): void;
  listOpen(): SignalLogRow[];
  totalExposure(): number;
  findByMarket(marketId: string): SignalLogRow | undefined;
}

export function createPositionTracker(deps: { signalRepo: SignalLogRepo }): PositionTracker {
  const open = new Map<string, SignalLogRow>();
  for (const row of deps.signalRepo.listOpen()) {
    open.set(row.signal_id, row);
  }

  return {
    open(signal) {
      deps.signalRepo.insert(signal);
      const row = deps.signalRepo.findById(signal.signal_id);
      /* c8 ignore next 2 */
      if (!row) throw new Error(`positionTracker.open: failed to read back ${signal.signal_id}`);
      open.set(row.signal_id, row);
    },
    close(signalId, fill) {
      deps.signalRepo.recordExit(signalId, fill);
      open.delete(signalId);
    },
    listOpen() {
      return Array.from(open.values());
    },
    totalExposure() {
      let sum = 0;
      for (const row of open.values()) sum += row.size_usdc;
      return sum;
    },
    findByMarket(marketId) {
      for (const row of open.values()) {
        if (row.market_id === marketId) return row;
      }
      return undefined;
    },
  };
}
