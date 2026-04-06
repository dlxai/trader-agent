const BUCKET_SIZE = 0.05;

export function priceBucket(price: number): number {
  if (price < 0 || price > 1) {
    throw new RangeError(`priceBucket: price ${price} not in [0, 1]`);
  }
  // Floor to nearest bucket, then round to 2 decimal places to avoid
  // floating-point representation issues (e.g., 0.6000000000000001).
  const raw = Math.floor(price / BUCKET_SIZE + 1e-9) * BUCKET_SIZE;
  return Math.round(raw * 100) / 100;
}

const DEAD_ZONE_MIN = 0.60;
const DEAD_ZONE_MAX = 0.85;
const DEAD_ZONE_PRIOR_WIN_RATE = 0.34;
const NEUTRAL_PRIOR_WIN_RATE = 0.50;

export function priorWinRate(bucket: number): number {
  if (bucket >= DEAD_ZONE_MIN && bucket <= DEAD_ZONE_MAX) {
    return DEAD_ZONE_PRIOR_WIN_RATE;
  }
  return NEUTRAL_PRIOR_WIN_RATE;
}
