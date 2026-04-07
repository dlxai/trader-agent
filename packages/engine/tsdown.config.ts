import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "collector/index": "src/collector/index.ts",
    "executor/index": "src/executor/index.ts",
    "db/index": "src/db/index.ts",
    "bus/index": "src/bus/index.ts",
    "config/index": "src/config/index.ts",
    "reviewer/index": "src/reviewer/index.ts",
    "recovery/index": "src/recovery/index.ts",
    "analyzer/index": "src/analyzer/index.ts",
    "util/index": "src/util/index.ts",
  },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["better-sqlite3", "ws"],
  outExtensions: () => ({ js: ".js", dts: ".d.ts" }),
  onSuccess: async () => {
    const { copyFileSync, mkdirSync } = await import("node:fs");
    const { join } = await import("node:path");
    mkdirSync(join(process.cwd(), "dist", "db"), { recursive: true });
    copyFileSync(
      join(process.cwd(), "src", "db", "schema.sql"),
      join(process.cwd(), "dist", "db", "schema.sql")
    );
  },
});
