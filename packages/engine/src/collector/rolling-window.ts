export interface Trade {
  timestampMs: number;
  address: string;
  sizeUsdc: number;
  side: "buy" | "sell";
  price: number;
}

export interface WindowStats {
  volume: number;
  netFlow: number;
  uniqueTraders: number;
  priceMove: number;
}

export interface RollingWindow {
  add(trade: Trade): void;
  stats(nowMs: number): WindowStats;
}

export interface RollingWindowOptions {
  windowMs: number;
}

export function createRollingWindow(opts: RollingWindowOptions): RollingWindow {
  const trades: Trade[] = [];

  function trim(nowMs: number): void {
    const cutoff = nowMs - opts.windowMs;
    while (trades.length > 0 && trades[0]!.timestampMs < cutoff) {
      trades.shift();
    }
  }

  return {
    add(trade: Trade): void {
      trades.push(trade);
    },
    stats(nowMs: number): WindowStats {
      trim(nowMs);
      if (trades.length === 0) {
        return { volume: 0, netFlow: 0, uniqueTraders: 0, priceMove: 0 };
      }
      let volume = 0;
      let netFlow = 0;
      const addresses = new Set<string>();
      for (const t of trades) {
        volume += t.sizeUsdc;
        netFlow += t.side === "buy" ? t.sizeUsdc : -t.sizeUsdc;
        addresses.add(t.address);
      }
      const priceMove = trades[trades.length - 1]!.price - trades[0]!.price;
      return {
        volume,
        netFlow,
        uniqueTraders: addresses.size,
        priceMove,
      };
    },
  };
}
