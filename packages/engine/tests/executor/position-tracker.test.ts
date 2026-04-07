import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPositionTracker } from "../../src/executor/position-tracker.js";

describe("positionTracker", () => {
  let db: Database.Database;
  let signalRepo: ReturnType<typeof createSignalLogRepo>;
  let tracker: ReturnType<typeof createPositionTracker>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    signalRepo = createSignalLogRepo(db);
    tracker = createPositionTracker({ signalRepo });
  });

  function sampleNew(signal_id: string, size_usdc = 100) {
    return {
      signal_id,
      market_id: "m1",
      market_title: "Test",
      resolves_at: Date.now() + 3_600_000,
      triggered_at: Date.now(),
      direction: "buy_yes" as const,
      entry_price: 0.55,
      price_bucket: 0.55,
      size_usdc,
      kelly_fraction: 0.1,
      snapshot_volume_1m: 3500,
      snapshot_net_flow_1m: 3200,
      snapshot_unique_traders_1m: 4,
      snapshot_price_move_5m: 0.04,
      snapshot_liquidity: 6000,
      llm_verdict: "real_signal" as const,
      llm_confidence: 0.72,
      llm_reasoning: "reason",
    };
  }

  it("loads empty state on first use", () => {
    expect(tracker.listOpen()).toHaveLength(0);
    expect(tracker.totalExposure()).toBe(0);
  });

  it("adds a new position and tracks exposure", () => {
    tracker.open(sampleNew("s1"));
    expect(tracker.listOpen()).toHaveLength(1);
    expect(tracker.totalExposure()).toBe(100);
  });

  it("closes position and removes from open set", () => {
    tracker.open(sampleNew("s2"));
    tracker.close("s2", {
      exit_at: Date.now() + 1000,
      exit_price: 0.60,
      exit_reason: "A_TP",
      pnl_gross_usdc: 9.0,
      fees_usdc: 0.5,
      slippage_usdc: 0.3,
      gas_usdc: 0.2,
      pnl_net_usdc: 8.0,
      holding_duration_sec: 1,
    });
    expect(tracker.listOpen()).toHaveLength(0);
  });

  it("recovers open positions from DB on construction", () => {
    tracker.open(sampleNew("recovery", 150));
    const tracker2 = createPositionTracker({ signalRepo });
    expect(tracker2.listOpen()).toHaveLength(1);
    expect(tracker2.totalExposure()).toBe(150);
  });

  it("findByMarket returns the open position for the given market", () => {
    tracker.open(sampleNew("find-me", 200));
    const found = tracker.findByMarket("m1");
    expect(found).toBeDefined();
    expect(found?.signal_id).toBe("find-me");
  });

  it("findByMarket returns undefined when no position is open for market", () => {
    const found = tracker.findByMarket("unknown-market");
    expect(found).toBeUndefined();
  });

  it("findByMarket skips positions on other markets (false branch of market_id check)", () => {
    // Open two positions on different markets so findByMarket must iterate past one
    const sig1 = sampleNew("sig-alpha", 100);
    sig1.market_id = "market-alpha";
    const sig2 = { ...sampleNew("sig-beta", 100), market_id: "market-beta" };
    tracker.open(sig1);
    tracker.open(sig2);
    const found = tracker.findByMarket("market-beta");
    expect(found?.signal_id).toBe("sig-beta");
    const notFound = tracker.findByMarket("market-gamma");
    expect(notFound).toBeUndefined();
  });
});
