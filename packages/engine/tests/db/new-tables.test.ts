import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";

describe("M1.7 new tables migration", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
  });

  it("creates chat_messages table with all required columns", () => {
    const cols = db.prepare("PRAGMA table_info(chat_messages)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("message_id");
    expect(names).toContain("agent_id");
    expect(names).toContain("role");
    expect(names).toContain("content");
    expect(names).toContain("model_used");
    expect(names).toContain("provider_used");
    expect(names).toContain("tokens_input");
    expect(names).toContain("tokens_output");
    expect(names).toContain("created_at");
  });

  it("creates coordinator_log table", () => {
    const cols = db.prepare("PRAGMA table_info(coordinator_log)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("log_id");
    expect(names).toContain("generated_at");
    expect(names).toContain("summary");
    expect(names).toContain("alerts");
    expect(names).toContain("suggestions");
    expect(names).toContain("context_snapshot");
  });

  it("creates llm_provider_state table", () => {
    const cols = db.prepare("PRAGMA table_info(llm_provider_state)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("provider_id");
    expect(names).toContain("is_connected");
    expect(names).toContain("auth_type");
    expect(names).toContain("models_available");
    expect(names).toContain("quota_used");
    expect(names).toContain("quota_limit");
  });

  it("creates app_state KV table", () => {
    const cols = db.prepare("PRAGMA table_info(app_state)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("key");
    expect(names).toContain("value");
    expect(names).toContain("updated_at");
  });

  it("rejects invalid agent_id in chat_messages", () => {
    expect(() =>
      db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run("invalid_agent", "user", "test", Date.now())
    ).toThrow();
  });

  it("rejects invalid role in chat_messages", () => {
    expect(() =>
      db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run("analyzer", "robot", "test", Date.now())
    ).toThrow();
  });
});
