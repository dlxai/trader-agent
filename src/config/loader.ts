import type { TraderConfig } from "./schema.js";
import { DEFAULT_CONFIG } from "./defaults.js";
import { readFileSync, existsSync } from "node:fs";

export function loadConfig(
  path: string | undefined,
  overrides: Partial<TraderConfig> = {}
): TraderConfig {
  let fromFile: Partial<TraderConfig> = {};
  if (path && existsSync(path)) {
    // Minimal YAML-lite: for v1, store config as JSON on disk. YAML support
    // deferred until M3 when Reviewer needs human-readable editing.
    const raw = readFileSync(path, "utf-8");
    fromFile = JSON.parse(raw) as Partial<TraderConfig>;
  }
  return { ...DEFAULT_CONFIG, ...fromFile, ...overrides };
}
