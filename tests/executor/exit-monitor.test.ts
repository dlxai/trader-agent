import { describe, it, expect } from "vitest";
import { evaluateExit } from "../../src/executor/exit-monitor.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { SignalLogRow } from "../../src/db/types.js";

function makeOpen(overrides: Partial<SignalLogRow> = {}): SignalLogRow {
  return {
    signal_id: "s1",
    market_id: "m1",
    market_title: "Test",
    resolves_at: Date.now() + 7_200_000,
    triggered_at: Date.now() - 60_000,
    direction: "buy_yes",
    entry_price: 0.50,
    price_bucket: 0.50,
    size_usdc: 100,
    kelly_fraction: 0.1,
    snapshot_volume_1m: 3500,
    snapshot_net_flow_1m: 3200,
    snapshot_unique_traders_1m: 4,
    snapshot_price_move_5m: 0.04,
    snapshot_liquidity: 6000,
    llm_verdict: "real_signal",
    llm_confidence: 0.72,
    llm_reasoning: "",
    exit_at: null,
    exit_price: null,
    exit_reason: null,
    pnl_gross_usdc: null,
    fees_usdc: null,
    slippage_usdc: null,
    gas_usdc: null,
    pnl_net_usdc: null,
    holding_duration_sec: null,
    ...overrides,
  };
}

describe("evaluateExit", () => {
  const cfg = DEFAULT_CONFIG;
  const now = Date.now();

  it("triggers E (expiry buffer) when close to resolution", () => {
    const position = makeOpen({ resolves_at: now + 60_000 });
    const result = evaluateExit(position, { currentPrice: 0.50, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("E");
  });

  it("triggers A-SL on -7% (normal)", () => {
    const position = makeOpen({ entry_price: 0.50 });
    const result = evaluateExit(position, { currentPrice: 0.46, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("A_SL");
  });

  it("triggers A-SL on -3% when late stage (< 30m to resolve)", () => {
    const position = makeOpen({ entry_price: 0.50, resolves_at: now + 1_200_000 });
    const result = evaluateExit(position, { currentPrice: 0.485, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("A_SL");
  });

  it("does NOT trigger A-SL at -1%", () => {
    const position = makeOpen({ entry_price: 0.50 });
    const result = evaluateExit(position, { currentPrice: 0.495, nowMs: now }, cfg);
    expect(result.exit).toBe(false);
  });

  it("triggers A-TP on +10%", () => {
    const position = makeOpen({ entry_price: 0.50 });
    const result = evaluateExit(position, { currentPrice: 0.55, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("A_TP");
  });

  it("triggers C on max holding time exceeded", () => {
    const position = makeOpen({ triggered_at: now - 14_500_000 });
    const result = evaluateExit(position, { currentPrice: 0.50, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("C");
  });

  it("E has highest priority: A-SL AND E both triggered → E wins", () => {
    const position = makeOpen({
      entry_price: 0.50,
      resolves_at: now + 60_000,
    });
    const result = evaluateExit(
      position,
      { currentPrice: 0.40, nowMs: now },
      cfg
    );
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("E");
  });

  it("handles buy_no direction (price direction inverted)", () => {
    const position = makeOpen({ direction: "buy_no", entry_price: 0.40 });
    const result = evaluateExit(position, { currentPrice: 0.428, nowMs: now }, cfg);
    expect(result.exit).toBe(true);
    expect(result.reason).toBe("A_SL");
  });
});
