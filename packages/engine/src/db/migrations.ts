import type Database from "better-sqlite3";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const MIGRATIONS_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "migrations"
);

const SCHEMA_SQL_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "schema.sql"
);

export function runMigrations(db: Database.Database): void {
  let txStarted = false;
  db.exec("BEGIN");
  txStarted = true;
  try {
    // 1. Run main schema.sql
    const schemaSql = readFileSync(SCHEMA_SQL_PATH, "utf-8");
    db.exec(schemaSql);

    // 2. Run numbered migration files in order
    const migrationFiles = readdirSync(MIGRATIONS_DIR)
      .filter(f => f.match(/^\d+_.*\.sql$/))
      .sort((a, b) => {
        const numA = parseInt(a.match(/^(\d+)/)?.[1] || "0");
        const numB = parseInt(b.match(/^(\d+)/)?.[1] || "0");
        return numA - numB;
      });

    for (const file of migrationFiles) {
      const version = parseInt(file.match(/^(\d+)/)?.[1] || "0");

      // Check if already applied
      const applied = db
        .prepare("SELECT 1 FROM schema_version WHERE version = ?")
            .get(version);

        if (!applied) {
          const sql = readFileSync(join(MIGRATIONS_DIR, file), "utf-8");
          db.exec(sql);

          // Mark as applied
          db.prepare("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)")
            .run(version, Date.now());

          console.log(`[migrations] Applied migration ${file}`);
        }
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
