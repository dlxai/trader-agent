import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@pmt/llm", "electron", "better-sqlite3", "ws"],
  outExtensions: () => ({ dts: ".d.ts" }),
});
