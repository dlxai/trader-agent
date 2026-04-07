import { describe, it, expect } from "vitest";
import { decideKillSwitch } from "../../src/reviewer/kill-switch-decider.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";

describe("decideKillSwitch", () => {
  it("does not kill with fewer than minTrades samples", () => {
    const decision = decideKillSwitch(
      { trade_count: 5, win_count: 1, win_rate: 0.2, total_pnl_net_usdc: -5 },
      DEFAULT_CONFIG
    );
    expect(decision.kill).toBe(false);
  });

  it("kills when trade_count >= min and win_rate < max_win_rate", () => {
    const decision = decideKillSwitch(
      { trade_count: 10, win_count: 3, win_rate: 0.30, total_pnl_net_usdc: -20 },
      DEFAULT_CONFIG
    );
    expect(decision.kill).toBe(true);
    expect(decision.reason).toContain("win rate 30.0%");
  });

  it("does not kill at exactly the threshold", () => {
    const decision = decideKillSwitch(
      { trade_count: 10, win_count: 5, win_rate: 0.50, total_pnl_net_usdc: 0 },
      DEFAULT_CONFIG
    );
    expect(decision.kill).toBe(false);
  });
});
