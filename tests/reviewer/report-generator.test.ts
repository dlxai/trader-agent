import { describe, it, expect } from "vitest";
import { generateReport } from "../../src/reviewer/report-generator.js";

describe("generateReport", () => {
  it("produces markdown with header, per-bucket stats, and recommendation", () => {
    const md = generateReport({
      period: "weekly",
      nowMs: new Date("2026-04-13T00:00:00Z").getTime(),
      buckets7d: [
        { price_bucket: 0.30, trade_count: 5, win_count: 4, win_rate: 0.8, total_pnl_net_usdc: 25 },
        { price_bucket: 0.50, trade_count: 12, win_count: 6, win_rate: 0.5, total_pnl_net_usdc: -5 },
      ],
      killSwitches: [],
      totalPnl7d: 20,
    });
    expect(md).toContain("# Polymarket Reviewer Report");
    expect(md).toContain("2026-04-13");
    expect(md).toContain("0.30");
    expect(md).toContain("80.0%");
    expect(md).toContain("0.50");
  });

  it("includes kill switch warnings prominently", () => {
    const md = generateReport({
      period: "weekly",
      nowMs: Date.now(),
      buckets7d: [],
      killSwitches: [
        { strategy: "smart_money_flow", reason: "win rate 30% over 10 trades" },
      ],
      totalPnl7d: -50,
    });
    expect(md).toMatch(/kill switch/i);
    expect(md).toContain("smart_money_flow");
  });
});
