import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    "polymarket-trader": "src/index.ts",
  },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  // Force .d.ts extension (tsdown defaults to .d.mts for esm; package.json expects .d.ts)
  outExtensions: () => ({ dts: ".d.ts" }),
  // Only external runtime deps — everything else (including plugin-sdk inline) is bundled
  external: ["better-sqlite3", "ws"],
  onSuccess: async () => {
    const { copyFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    copyFileSync(
      join(process.cwd(), "openclaw.plugin.json"),
      join(process.cwd(), "dist", "openclaw.plugin.json")
    );
  },
});
