import type Database from "better-sqlite3";

export type PerformanceWindow = "7d" | "30d";

export interface StrategyPerformanceRow {
  price_bucket: number;
  window: PerformanceWindow;
  trade_count: number;
  win_count: number;
  win_rate: number;
  total_pnl_net_usdc: number;
  last_updated: number;
}

export interface StrategyPerformanceRepo {
  upsert(row: StrategyPerformanceRow): void;
  get(bucket: number, window: PerformanceWindow): StrategyPerformanceRow | null;
  listByWindow(window: PerformanceWindow): StrategyPerformanceRow[];
}

export function createStrategyPerformanceRepo(db: Database.Database): StrategyPerformanceRepo {
  const upsertStmt = db.prepare(`
    INSERT OR REPLACE INTO strategy_performance
      (price_bucket, window, trade_count, win_count, win_rate, total_pnl_net_usdc, last_updated)
    VALUES
      (@price_bucket, @window, @trade_count, @win_count, @win_rate, @total_pnl_net_usdc, @last_updated)
  `);

  const getStmt = db.prepare(`
    SELECT price_bucket, window, trade_count, win_count, win_rate, total_pnl_net_usdc, last_updated
    FROM strategy_performance
    WHERE price_bucket = ? AND window = ?
  `);

  const listByWindowStmt = db.prepare(`
    SELECT price_bucket, window, trade_count, win_count, win_rate, total_pnl_net_usdc, last_updated
    FROM strategy_performance
    WHERE window = ?
    ORDER BY price_bucket ASC
  `);

  return {
    upsert(row) {
      upsertStmt.run({
        price_bucket: row.price_bucket,
        window: row.window,
        trade_count: row.trade_count,
        win_count: row.win_count,
        win_rate: row.win_rate,
        total_pnl_net_usdc: row.total_pnl_net_usdc,
        last_updated: row.last_updated,
      });
    },

    get(bucket, window) {
      return (getStmt.get(bucket, window) as StrategyPerformanceRow | undefined) ?? null;
    },

    listByWindow(window) {
      return listByWindowStmt.all(window) as StrategyPerformanceRow[];
    },
  };
}
