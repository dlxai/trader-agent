/**
 * Polymarket Trader plugin entry point.
 *
 * Task 1.5: now uses the inlined plugin SDK. Task 28 will add full wiring.
 *
 * See docs/specs/2026-04-06-polymarket-trading-agents-design.md for design.
 */
import { definePlugin } from "./plugin-sdk.js";
import type { PluginApi } from "./plugin-sdk.js";

export default definePlugin({
  id: "polymarket-trader",
  name: "Polymarket Trader",

  setup(api: PluginApi) {
    api.logger.info("[polymarket] plugin activated (bootstrap only — no runtime yet)");
  },
});
