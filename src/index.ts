/**
 * Polymarket Trader plugin entry point.
 *
 * This file is a bootstrap stub. Task 1.5 will refactor it to use the
 * inlined plugin SDK at ./plugin-sdk.ts. Task 28 (plugin wiring) will
 * then add the full Collector/Executor/Analyzer wiring.
 *
 * See docs/specs/2026-04-06-polymarket-trading-agents-design.md for design.
 */

// Bootstrap export — a no-op default export so the file is a valid ES module.
// The real plugin definition arrives in Task 1.5.
export default {
  id: "polymarket-trader",
  name: "Polymarket Trader",
  activate(): void {
    // intentional no-op until Task 1.5 wires up the inlined plugin SDK
    console.log("[polymarket] bootstrap plugin loaded (no runtime yet)");
  },
  register(): void {
    this.activate();
  },
};
