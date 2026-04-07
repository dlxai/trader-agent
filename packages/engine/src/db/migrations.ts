import type Database from "better-sqlite3";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const SCHEMA_SQL_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "schema.sql"
);
const CURRENT_VERSION = 1;

export function runMigrations(db: Database.Database): void {
  const schemaSql = readFileSync(SCHEMA_SQL_PATH, "utf-8");
  let txStarted = false;
  db.exec("BEGIN");
  txStarted = true;
  try {
    db.exec(schemaSql);
    const existing = db
      .prepare("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
      .get() as { version: number } | undefined;
    if (!existing || existing.version < CURRENT_VERSION) {
      db.prepare("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)").run(
        CURRENT_VERSION,
        Date.now()
      );
    }
    db.exec("COMMIT");
  } catch (err) {
    if (txStarted) db.exec("ROLLBACK");
    throw err;
  }
}

export function currentSchemaVersion(db: Database.Database): number {
  const row = db
    .prepare("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    .get() as { version: number } | undefined;
  return row?.version ?? 0;
}
