import type { TraderConfig } from "./schema.js";
import { DEFAULT_CONFIG } from "./defaults.js";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

/**
 * Load configuration from multiple sources (priority: env > file > defaults)
 */
export function loadConfig(
  path: string | undefined,
  overrides: Partial<TraderConfig> = {}
): TraderConfig {
  // 1. Start with defaults
  let config: TraderConfig = { ...DEFAULT_CONFIG };

  // 2. Load from file if provided or found in standard locations
  const configPath = path || findConfigFile();
  if (configPath && existsSync(configPath)) {
    try {
      const raw = readFileSync(configPath, "utf-8");
      // Remove JSON comments (lines starting with // or containing //)
      const cleaned = raw.replace(/\/\/.*$/gm, '');
      const fromFile = JSON.parse(cleaned) as Partial<TraderConfig>;
      config = { ...config, ...fromFile };
    } catch (err) {
      console.error(`[config] Failed to load config from ${configPath}: ${String(err)}`);
    }
  }

  // 3. Apply environment variable overrides
  config = applyEnvOverrides(config);

  // 4. Apply explicit overrides (highest priority)
  config = { ...config, ...overrides };

  return config;
}

/**
 * Find config file in standard locations
 */
function findConfigFile(): string | undefined {
  const candidates = [
    process.env.POLYMARKET_TRADER_CONFIG,
    join(process.cwd(), 'config.json'),
    join(process.cwd(), 'polymarket-trader.json'),
    join(process.env.HOME || process.env.USERPROFILE || '', '.polymarket-trader', 'config.json'),
  ].filter(Boolean) as string[];

  for (const path of candidates) {
    if (existsSync(path)) {
      return path;
    }
  }
  return undefined;
}

/**
 * Apply environment variable overrides
 */
function applyEnvOverrides(config: TraderConfig): TraderConfig {
  const envMappings: Record<string, (val: string, cfg: TraderConfig) => void> = {
    POLYMARKET_MIN_TRADE_USDC: (v, c) => c.minTradeUsdc = Number(v),
    POLYMARKET_MIN_NET_FLOW_USDC: (v, c) => c.minNetFlow1mUsdc = Number(v),
    POLYMARKET_MIN_UNIQUE_TRADERS: (v, c) => c.minUniqueTraders1m = Number(v),
    POLYMARKET_MIN_PRICE_MOVE: (v, c) => c.minPriceMove5m = Number(v),
    POLYMARKET_MIN_LIQUIDITY_USDC: (v, c) => c.minLiquidityUsdc = Number(v),
    POLYMARKET_MAX_POSITION_USDC: (v, c) => c.maxPositionUsdc = Number(v),
    POLYMARKET_MAX_OPEN_POSITIONS: (v, c) => c.maxOpenPositions = Number(v),
    POLYMARKET_DAILY_LOSS_HALT_PCT: (v, c) => c.dailyLossHaltPct = Number(v),
    POLYMARKET_WEEKLY_LOSS_HALT_PCT: (v, c) => c.weeklyLossHaltPct = Number(v),
    POLYMARKET_STOP_LOSS_PCT: (v, c) => c.stopLossPctNormal = Number(v),
    POLYMARKET_TAKE_PROFIT_PCT: (v, c) => c.takeProfitPct = Number(v),
    POLYMARKET_CLOB_WS_URL: (v, c) => c.polymarketClobWsUrl = v,
    POLYMARKET_ACTIVITY_WS_URL: (v, c) => c.polymarketActivityWsUrl = v,
    POLYMARKET_ANALYZER_MODEL: (v, c) => c.analyzerModel = v,
    POLYMARKET_LLM_TIMEOUT_MS: (v, c) => c.llmTimeoutMs = Number(v),
  };

  for (const [envVar, setter] of Object.entries(envMappings)) {
    const value = process.env[envVar];
    if (value !== undefined) {
      try {
        setter(value, config);
        console.log(`[config] Override from env: ${envVar}`);
      } catch (err) {
        console.error(`[config] Failed to apply ${envVar}: ${String(err)}`);
      }
    }
  }

  return config;
}
