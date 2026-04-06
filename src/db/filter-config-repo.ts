import type Database from "better-sqlite3";

export interface FilterConfigEntry {
  key: string;
  value: string;
  source: string;
  updated_at: number;
}

export interface FilterConfigRepo {
  get(key: string): FilterConfigEntry | null;
  set(key: string, value: string, source: string): void;
  listAll(): FilterConfigEntry[];
}

export function createFilterConfigRepo(db: Database.Database): FilterConfigRepo {
  const getStmt = db.prepare(
    "SELECT key, value, source, updated_at FROM filter_config WHERE key = ?"
  );
  const upsertStmt = db.prepare(`
    INSERT INTO filter_config (key, value, source, updated_at)
    VALUES (@key, @value, @source, @updated_at)
    ON CONFLICT(key) DO UPDATE SET
      value = excluded.value,
      source = excluded.source,
      updated_at = excluded.updated_at
  `);
  const listStmt = db.prepare(
    "SELECT key, value, source, updated_at FROM filter_config ORDER BY key"
  );

  return {
    get(key) {
      return (getStmt.get(key) as FilterConfigEntry | undefined) ?? null;
    },
    set(key, value, source) {
      upsertStmt.run({ key, value, source, updated_at: Date.now() });
    },
    listAll() {
      return listStmt.all() as FilterConfigEntry[];
    },
  };
}
