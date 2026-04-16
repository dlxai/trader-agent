import { defineConfig } from "tsdown";

// Main process is ESM (package.json "type": "module"), but Electron's
// sandboxed preload scripts must be CommonJS — an ESM preload silently
// fails to load and leaves window.pmt undefined in the renderer.
// So we build the two entries with different formats.
export default defineConfig([
  {
    entry: { index: "src/index.ts" },
    format: ["esm"],
    dts: true,
    clean: true,
    sourcemap: false,
    external: ["@pmt/engine", "@pmt/llm", "electron", "better-sqlite3", "ws"],
    outExtensions: () => ({ js: ".js", dts: ".d.ts" }),
  },
  {
    entry: { preload: "src/preload.ts" },
    format: ["cjs"],
    dts: true,
    clean: false,
    sourcemap: false,
    external: ["electron"],
    outExtensions: () => ({ js: ".cjs", dts: ".d.cts" }),
  },
]);
