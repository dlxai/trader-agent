import { describe, it, expect } from "vitest";
import { loadConfig } from "../../src/config/loader.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";

describe("loadConfig", () => {
  it("returns defaults when no path given", () => {
    const cfg = loadConfig(undefined);
    expect(cfg).toEqual(DEFAULT_CONFIG);
  });

  it("overrides specific fields from partial overrides", () => {
    const cfg = loadConfig(undefined, { minNetFlow1mUsdc: 5000, kellyMultiplier: 0.5 });
    expect(cfg.minNetFlow1mUsdc).toBe(5000);
    expect(cfg.kellyMultiplier).toBe(0.5);
    expect(cfg.minTradeUsdc).toBe(DEFAULT_CONFIG.minTradeUsdc);
  });
});
