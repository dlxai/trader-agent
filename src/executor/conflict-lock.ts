export interface ConflictLock {
  tryAcquire(marketId: string): boolean;
  release(marketId: string): void;
  isHeld(marketId: string): boolean;
}

export function createConflictLock(): ConflictLock {
  const held = new Set<string>();
  return {
    tryAcquire(marketId) {
      if (held.has(marketId)) return false;
      held.add(marketId);
      return true;
    },
    release(marketId) {
      held.delete(marketId);
    },
    isHeld(marketId) {
      return held.has(marketId);
    },
  };
}
