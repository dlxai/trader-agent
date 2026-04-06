export function nowMs(): number {
  return Date.now();
}

export function secondsUntil(targetMs: number, from: number = nowMs()): number {
  return Math.floor((targetMs - from) / 1000);
}

export function isWithinBufferOfExpiry(
  resolvesAtMs: number,
  bufferSec: number,
  nowMsValue: number = nowMs()
): boolean {
  return secondsUntil(resolvesAtMs, nowMsValue) <= bufferSec;
}
