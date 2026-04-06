import type Database from "better-sqlite3";

export interface PortfolioState {
  total_capital: number;
  current_equity: number;
  day_start_equity: number;
  week_start_equity: number;
  peak_equity: number;
  current_drawdown: number;
  daily_halt_triggered: boolean;
  weekly_halt_triggered: boolean;
}

const DEFAULTS: PortfolioState = {
  total_capital: 10_000,
  current_equity: 10_000,
  day_start_equity: 10_000,
  week_start_equity: 10_000,
  peak_equity: 10_000,
  current_drawdown: 0,
  daily_halt_triggered: false,
  weekly_halt_triggered: false,
};

export interface PortfolioStateRepo {
  read(): PortfolioState;
  update(patch: Partial<PortfolioState>): void;
}

function serialize(value: unknown): string {
  return JSON.stringify(value);
}
function deserialize<T>(raw: string | undefined, fallback: T): T {
  if (raw === undefined) return fallback;
  return JSON.parse(raw) as T;
}

export function createPortfolioStateRepo(db: Database.Database): PortfolioStateRepo {
  const getStmt = db.prepare("SELECT key, value FROM portfolio_state");
  const upsertStmt = db.prepare(`
    INSERT INTO portfolio_state (key, value, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
  `);

  function read(): PortfolioState {
    const rows = getStmt.all() as Array<{ key: string; value: string }>;
    const map = new Map(rows.map((r) => [r.key, r.value]));
    return {
      total_capital: deserialize(map.get("total_capital"), DEFAULTS.total_capital),
      current_equity: deserialize(map.get("current_equity"), DEFAULTS.current_equity),
      day_start_equity: deserialize(map.get("day_start_equity"), DEFAULTS.day_start_equity),
      week_start_equity: deserialize(map.get("week_start_equity"), DEFAULTS.week_start_equity),
      peak_equity: deserialize(map.get("peak_equity"), DEFAULTS.peak_equity),
      current_drawdown: deserialize(map.get("current_drawdown"), DEFAULTS.current_drawdown),
      daily_halt_triggered: deserialize(map.get("daily_halt_triggered"), DEFAULTS.daily_halt_triggered),
      weekly_halt_triggered: deserialize(map.get("weekly_halt_triggered"), DEFAULTS.weekly_halt_triggered),
    };
  }

  function update(patch: Partial<PortfolioState>): void {
    const now = Date.now();
    const tx = db.transaction((entries: Array<[string, string]>) => {
      for (const [k, v] of entries) upsertStmt.run(k, v, now);
    });
    tx(Object.entries(patch).map(([k, v]) => [k, serialize(v)]));
  }

  return { read, update };
}
