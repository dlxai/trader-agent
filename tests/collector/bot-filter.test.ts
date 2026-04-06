import { describe, it, expect } from "vitest";
import { createBotFilter } from "../../src/collector/bot-filter.js";

describe("botFilter", () => {
  it("allows first 10 trades from an address within 1s", () => {
    const filter = createBotFilter({ burstCount: 10, windowMs: 1000 });
    for (let i = 0; i < 10; i++) {
      expect(filter.isBot("0xabc", 1_000 + i * 10)).toBe(false);
    }
  });

  it("marks address as bot on 11th trade within 1s", () => {
    const filter = createBotFilter({ burstCount: 10, windowMs: 1000 });
    for (let i = 0; i < 10; i++) filter.isBot("0xabc", 1_000 + i * 10);
    expect(filter.isBot("0xabc", 1_050)).toBe(true);
  });

  it("keeps bot classification sticky for the session", () => {
    const filter = createBotFilter({ burstCount: 10, windowMs: 1000 });
    for (let i = 0; i < 11; i++) filter.isBot("0xabc", 1_000 + i * 10);
    expect(filter.isBot("0xabc", 10_000_000)).toBe(true);
  });

  it("tracks different addresses independently", () => {
    const filter = createBotFilter({ burstCount: 10, windowMs: 1000 });
    for (let i = 0; i < 11; i++) filter.isBot("0xabc", 1_000 + i * 10);
    expect(filter.isBot("0xdef", 1_000)).toBe(false);
  });

  it("does not count trades outside the rolling window", () => {
    const filter = createBotFilter({ burstCount: 10, windowMs: 1000 });
    for (let i = 0; i < 10; i++) filter.isBot("0xabc", 1_000 + i * 50);
    expect(filter.isBot("0xabc", 3_000)).toBe(false);
  });
});
