import type { TraderConfig } from "../config/schema.js";

export interface KellyInput {
  entryPrice: number;
  winRate: number;
  capital: number;
  config: TraderConfig;
}

export interface KellyResult {
  size: number;
  kellyFraction: number;
  reason: "ok" | "kelly_non_positive" | "below_min_position";
}

export function calculateKellyPosition(input: KellyInput): KellyResult {
  const { entryPrice, winRate, capital, config } = input;
  const payoffRatio = (1 - entryPrice) / entryPrice;
  const rawKelly = (winRate * payoffRatio - (1 - winRate)) / payoffRatio;
  const kellyFraction = rawKelly * config.kellyMultiplier;

  if (kellyFraction <= 0) {
    return { size: 0, kellyFraction, reason: "kelly_non_positive" };
  }

  let size = capital * kellyFraction;
  size = Math.min(size, config.maxPositionUsdc);
  const maxSizeByLoss = config.maxSingleTradeLossUsdc / entryPrice;
  size = Math.min(size, maxSizeByLoss);
  size = Math.floor(size);

  if (size < config.minPositionUsdc) {
    return { size: 0, kellyFraction, reason: "below_min_position" };
  }
  return { size, kellyFraction, reason: "ok" };
}
