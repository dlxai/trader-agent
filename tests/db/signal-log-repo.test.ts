import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import type { NewSignal } from "../../src/db/types.js";

function sample(overrides: Partial<NewSignal> = {}): NewSignal {
  return {
    signal_id: "sig-1",
    market_id: "mkt-1",
    market_title: "Will it rain?",
    resolves_at: 1_700_000_000_000,
    triggered_at: 1_699_000_000_000,
    direction: "buy_yes",
    entry_price: 0.55,
    price_bucket: 0.55,
    size_usdc: 100,
    kelly_fraction: 0.1,
    snapshot_volume_1m: 3500,
    snapshot_net_flow_1m: 3200,
    snapshot_unique_traders_1m: 4,
    snapshot_price_move_5m: 0.04,
    snapshot_liquidity: 6000,
    llm_verdict: "real_signal",
    llm_confidence: 0.72,
    llm_reasoning: "strong net flow + 4 unique traders",
    ...overrides,
  };
}

describe("signalLogRepo", () => {
  let db: Database.Database;
  let repo: ReturnType<typeof createSignalLogRepo>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    repo = createSignalLogRepo(db);
  });

  it("inserts a new signal and reads it back", () => {
    repo.insert(sample());
    const row = repo.findById("sig-1");
    expect(row).not.toBeNull();
    expect(row?.market_title).toBe("Will it rain?");
    expect(row?.exit_at).toBeNull();
    expect(row?.pnl_net_usdc).toBeNull();
  });

  it("lists open positions (exit_at IS NULL)", () => {
    repo.insert(sample({ signal_id: "open-1" }));
    repo.insert(sample({ signal_id: "open-2", market_id: "mkt-2" }));
    const open = repo.listOpen();
    expect(open).toHaveLength(2);
    expect(open.map((r) => r.signal_id).sort()).toEqual(["open-1", "open-2"]);
  });

  it("records exit and moves signal to closed", () => {
    repo.insert(sample({ signal_id: "close-1" }));
    repo.recordExit("close-1", {
      exit_at: 1_699_001_000_000,
      exit_price: 0.60,
      exit_reason: "A_TP",
      pnl_gross_usdc: 9.0,
      fees_usdc: 0.5,
      slippage_usdc: 0.3,
      gas_usdc: 0.2,
      pnl_net_usdc: 8.0,
      holding_duration_sec: 1000,
    });
    const row = repo.findById("close-1");
    expect(row?.exit_reason).toBe("A_TP");
    expect(row?.pnl_net_usdc).toBe(8.0);
    expect(repo.listOpen()).toHaveLength(0);
  });
});
