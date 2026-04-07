import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createKillSwitchRepo } from "../../src/db/kill-switch-repo.js";

describe("killSwitchRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createKillSwitchRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createKillSwitchRepo(db);
  });

  it("returns null when no kill switch exists for a strategy", () => {
    expect(repo.get("smart_money_flow")).toBeNull();
  });

  it("inserts a kill record with default 'killed' status", () => {
    repo.kill("smart_money_flow", {
      reason: "win rate 30% over 10 trades",
      trigger_win_rate: 0.30,
      trigger_sample_size: 10,
    });
    const row = repo.get("smart_money_flow");
    expect(row).not.toBeNull();
    expect(row?.strategy).toBe("smart_money_flow");
    expect(row?.status).toBe("killed");
    expect(row?.reason).toBe("win rate 30% over 10 trades");
    expect(row?.trigger_win_rate).toBe(0.30);
    expect(row?.reviewed_at).toBeNull();
  });

  it("re-killing same strategy replaces the row", () => {
    repo.kill("strat-x", { reason: "first", trigger_win_rate: 0.4, trigger_sample_size: 10 });
    repo.kill("strat-x", { reason: "second", trigger_win_rate: 0.3, trigger_sample_size: 15 });
    const row = repo.get("strat-x");
    expect(row?.reason).toBe("second");
    expect(row?.trigger_sample_size).toBe(15);
  });

  it("reviewKill marks the row as reviewed (keep_killed or reenabled)", () => {
    repo.kill("strat-y", { reason: "x", trigger_win_rate: 0.3, trigger_sample_size: 10 });
    repo.review("strat-y", "reviewed_reenabled");
    const row = repo.get("strat-y");
    expect(row?.status).toBe("reviewed_reenabled");
    expect(row?.reviewed_at).not.toBeNull();
  });

  it("listKilled returns only rows with status='killed' (not yet reviewed)", () => {
    repo.kill("alive", { reason: "x", trigger_win_rate: 0.3, trigger_sample_size: 10 });
    repo.kill("dead", { reason: "y", trigger_win_rate: 0.2, trigger_sample_size: 12 });
    repo.review("dead", "reviewed_keep_killed");
    const killed = repo.listKilled();
    expect(killed).toHaveLength(1);
    expect(killed[0]?.strategy).toBe("alive");
  });
});
