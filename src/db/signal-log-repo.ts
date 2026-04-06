import type Database from "better-sqlite3";
import type { SignalLogRow, NewSignal, ExitFill } from "./types.js";

export interface SignalLogRepo {
  insert(signal: NewSignal): void;
  findById(id: string): SignalLogRow | null;
  listOpen(): SignalLogRow[];
  recordExit(id: string, fill: ExitFill): void;
  listClosedSince(sinceMs: number): SignalLogRow[];
}

export function createSignalLogRepo(db: Database.Database): SignalLogRepo {
  const insertStmt = db.prepare(`
    INSERT INTO signal_log (
      signal_id, market_id, market_title, resolves_at, triggered_at,
      direction, entry_price, price_bucket, size_usdc, kelly_fraction,
      snapshot_volume_1m, snapshot_net_flow_1m, snapshot_unique_traders_1m,
      snapshot_price_move_5m, snapshot_liquidity,
      llm_verdict, llm_confidence, llm_reasoning
    ) VALUES (
      @signal_id, @market_id, @market_title, @resolves_at, @triggered_at,
      @direction, @entry_price, @price_bucket, @size_usdc, @kelly_fraction,
      @snapshot_volume_1m, @snapshot_net_flow_1m, @snapshot_unique_traders_1m,
      @snapshot_price_move_5m, @snapshot_liquidity,
      @llm_verdict, @llm_confidence, @llm_reasoning
    )
  `);

  const findByIdStmt = db.prepare("SELECT * FROM signal_log WHERE signal_id = ?");
  const listOpenStmt = db.prepare("SELECT * FROM signal_log WHERE exit_at IS NULL");
  const listClosedSinceStmt = db.prepare(
    "SELECT * FROM signal_log WHERE exit_at IS NOT NULL AND exit_at >= ? ORDER BY exit_at DESC"
  );
  const recordExitStmt = db.prepare(`
    UPDATE signal_log SET
      exit_at = @exit_at,
      exit_price = @exit_price,
      exit_reason = @exit_reason,
      pnl_gross_usdc = @pnl_gross_usdc,
      fees_usdc = @fees_usdc,
      slippage_usdc = @slippage_usdc,
      gas_usdc = @gas_usdc,
      pnl_net_usdc = @pnl_net_usdc,
      holding_duration_sec = @holding_duration_sec
    WHERE signal_id = @signal_id AND exit_at IS NULL
  `);

  return {
    insert(signal) {
      insertStmt.run(signal);
    },
    findById(id) {
      return (findByIdStmt.get(id) as SignalLogRow | undefined) ?? null;
    },
    listOpen() {
      return listOpenStmt.all() as SignalLogRow[];
    },
    recordExit(id, fill) {
      const result = recordExitStmt.run({ signal_id: id, ...fill });
      if (result.changes !== 1) {
        throw new Error(`recordExit: expected 1 row updated, got ${result.changes} for ${id}`);
      }
    },
    listClosedSince(sinceMs) {
      return listClosedSinceStmt.all(sinceMs) as SignalLogRow[];
    },
  };
}
