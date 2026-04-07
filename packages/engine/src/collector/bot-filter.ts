export interface BotFilterOptions {
  burstCount: number;
  windowMs: number;
}

export interface BotFilter {
  /** Returns true if the address is classified as a bot AT OR AFTER this trade. */
  isBot(address: string, timestampMs: number): boolean;
}

export function createBotFilter(opts: BotFilterOptions): BotFilter {
  const tradesByAddress = new Map<string, number[]>();
  const knownBots = new Set<string>();

  return {
    isBot(address: string, timestampMs: number): boolean {
      if (knownBots.has(address)) return true;

      let trades = tradesByAddress.get(address);
      if (!trades) {
        trades = [];
        tradesByAddress.set(address, trades);
      }
      const cutoff = timestampMs - opts.windowMs;
      while (trades.length > 0 && trades[0]! < cutoff) {
        trades.shift();
      }
      trades.push(timestampMs);

      if (trades.length > opts.burstCount) {
        knownBots.add(address);
        tradesByAddress.delete(address);
        return true;
      }
      return false;
    },
  };
}
