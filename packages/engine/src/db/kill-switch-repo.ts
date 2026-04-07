import type Database from "better-sqlite3";

export type KillSwitchStatus = "killed" | "reviewed_keep_killed" | "reviewed_reenabled";

export interface KillSwitchRow {
  strategy: string;
  killed_at: number;
  reason: string;
  trigger_win_rate: number;
  trigger_sample_size: number;
  status: KillSwitchStatus;
  reviewed_at: number | null;
}

export interface KillSwitchRepo {
  get(strategy: string): KillSwitchRow | null;
  kill(
    strategy: string,
    info: { reason: string; trigger_win_rate: number; trigger_sample_size: number }
  ): void;
  review(strategy: string, newStatus: "reviewed_keep_killed" | "reviewed_reenabled"): void;
  listKilled(): KillSwitchRow[];
}

export function createKillSwitchRepo(db: Database.Database): KillSwitchRepo {
  const getStmt = db.prepare(
    "SELECT strategy, killed_at, reason, trigger_win_rate, trigger_sample_size, status, reviewed_at FROM strategy_kill_switch WHERE strategy = ?"
  );
  const killStmt = db.prepare(`
    INSERT OR REPLACE INTO strategy_kill_switch
      (strategy, killed_at, reason, trigger_win_rate, trigger_sample_size, status, reviewed_at)
    VALUES
      (@strategy, @killed_at, @reason, @trigger_win_rate, @trigger_sample_size, 'killed', NULL)
  `);
  const reviewStmt = db.prepare(`
    UPDATE strategy_kill_switch
    SET status = @status, reviewed_at = @reviewed_at
    WHERE strategy = @strategy
  `);
  const listKilledStmt = db.prepare(
    "SELECT strategy, killed_at, reason, trigger_win_rate, trigger_sample_size, status, reviewed_at FROM strategy_kill_switch WHERE status = 'killed' ORDER BY killed_at DESC"
  );

  return {
    get(strategy) {
      return (getStmt.get(strategy) as KillSwitchRow | undefined) ?? null;
    },
    kill(strategy, info) {
      killStmt.run({
        strategy,
        killed_at: Date.now(),
        reason: info.reason,
        trigger_win_rate: info.trigger_win_rate,
        trigger_sample_size: info.trigger_sample_size,
      });
    },
    review(strategy, newStatus) {
      const result = reviewStmt.run({
        strategy,
        status: newStatus,
        reviewed_at: Date.now(),
      });
      if (result.changes !== 1) {
        throw new Error(`review: expected 1 row updated, got ${result.changes} for ${strategy}`);
      }
    },
    listKilled() {
      return listKilledStmt.all() as KillSwitchRow[];
    },
  };
}
