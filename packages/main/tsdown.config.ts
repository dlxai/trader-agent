import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    preload: "src/preload.ts",
  },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@pmt/llm", "electron", "better-sqlite3", "ws"],
  outExtensions: () => ({ js: ".js", dts: ".d.ts" }),
});
