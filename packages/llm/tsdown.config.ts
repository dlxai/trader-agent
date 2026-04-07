import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@anthropic-ai/sdk", "openai", "@google/generative-ai"],
  outExtensions: () => ({ js: ".js", dts: ".d.ts" }),
});
