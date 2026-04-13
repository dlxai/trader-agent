import type { TraderConfig } from "../config/schema.js";
import type { EventBus } from "../bus/events.js";
import type { SignalLogRepo } from "../db/signal-log-repo.js";
import type { PortfolioStateRepo } from "../db/portfolio-state-repo.js";
import type { VerdictEvent } from "../bus/types.js";
import type { NewSignal, SignalLogRow, ExitReason } from "../db/types.js";
import type { OrderFiller } from "./order-filler.js";
import { calculateKellyPosition } from "./kelly.js";
import { priceBucket, priorWinRate } from "./price-bucket.js";
import { createPositionTracker } from "./position-tracker.js";
import { createCircuitBreaker } from "./circuit-breaker.js";
import { createConflictLock } from "./conflict-lock.js";
import { computePnL } from "./pnl.js";
import { evaluateExit } from "./exit-monitor.js";
import { createDrawdownGuard } from "./drawdown-guard.js";
import { randomUUID } from "node:crypto";

export interface ExecutorDeps {
  config: TraderConfig;
  bus: EventBus;
  signalRepo: SignalLogRepo;
  portfolioRepo: PortfolioStateRepo;
  filler: OrderFiller;
  logger: { info: (m: string) => void; warn: (m: string) => void; error: (m: string) => void };
}

export interface Executor {
  /** Returns signal_id on success, null if rejected. */
  handleVerdict(event: VerdictEvent): Promise<string | null>;
  onPriceTick(marketId: string, currentMidPrice: number, nowMs: number): Promise<void>;
  closePosition(pos: SignalLogRow, exitMidPrice: number, nowMs: number, reason: ExitReason): Promise<void>;
  openPositions(): SignalLogRow[];
  getLastPrice(marketId: string): number | undefined;
}

export function createExecutor(deps: ExecutorDeps): Executor {
  const tracker = createPositionTracker({ signalRepo: deps.signalRepo });
  const breaker = createCircuitBreaker({ config: deps.config, portfolioRepo: deps.portfolioRepo });
  const lock = createConflictLock();
  const drawdownGuard = createDrawdownGuard(deps.config.drawdownGuard);
  const lastPriceMap = new Map<string, number>();

  // Re-acquire locks for positions loaded from DB on startup
  for (const pos of tracker.listOpen()) lock.tryAcquire(pos.market_id);

  // Reverse signal handling (Rule D) — subscribe to bus
  deps.bus.onTrigger((event) => {
    for (const pos of tracker.listOpen()) {
      if (pos.market_id === event.market_id && pos.direction !== event.direction) {
        closePosition(pos, event.snapshot.current_mid_price, event.triggered_at, "D");
      }
    }
  });

  async function handleVerdict(event: VerdictEvent): Promise<string | null> {
    if (event.verdict !== "real_signal") {
      deps.logger.info(`[executor] verdict not actionable: ${event.verdict}`);
      return null;
    }
    if (!breaker.canOpenNewPosition()) {
      deps.logger.warn("[executor] circuit breaker blocks new position");
      return null;
    }
    if (tracker.totalExposure() + deps.config.minPositionUsdc > deps.config.maxTotalPositionUsdc) {
      deps.logger.warn("[executor] total exposure cap reached");
      return null;
    }
    if (tracker.listOpen().length >= deps.config.maxOpenPositions) {
      deps.logger.warn("[executor] max open positions reached");
      return null;
    }
    if (!lock.tryAcquire(event.trigger.market_id)) {
      deps.logger.info(`[executor] market ${event.trigger.market_id} already held, rejecting`);
      return null;
    }

    const state = deps.portfolioRepo.read();
    const entryPrice = event.trigger.snapshot.current_mid_price;
    const bucket = priceBucket(entryPrice);
    const winRate = priorWinRate(bucket); // Phase 8 will replace with strategy_performance lookup
    const kelly = calculateKellyPosition({
      entryPrice,
      winRate,
      capital: state.current_equity,
      config: deps.config,
    });
    if (kelly.size === 0) {
      deps.logger.info(`[executor] kelly size 0 (${kelly.reason})`);
      lock.release(event.trigger.market_id);
      return null;
    }

    const fill = await deps.filler.fillBuy({
      tokenId: event.trigger.market_id,
      midPrice: entryPrice,
      sizeUsdc: kelly.size,
      direction: event.llm_direction,
      timestampMs: event.trigger.triggered_at,
    });

    if (!fill.filled) {
      deps.logger.warn(`[executor] fill failed: ${fill.reason}`);
      lock.release(event.trigger.market_id);
      return null;
    }

    const newSignal: NewSignal = {
      signal_id: randomUUID(),
      market_id: event.trigger.market_id,
      market_title: event.trigger.market_title,
      resolves_at: event.trigger.resolves_at,
      triggered_at: event.trigger.triggered_at,
      direction: event.llm_direction,
      entry_price: fill.fillPrice,
      price_bucket: bucket,
      size_usdc: fill.filledSize,
      kelly_fraction: kelly.kellyFraction,
      snapshot_volume_1m: event.trigger.snapshot.volume_1m,
      snapshot_net_flow_1m: event.trigger.snapshot.net_flow_1m,
      snapshot_unique_traders_1m: event.trigger.snapshot.unique_traders_1m,
      snapshot_price_move_5m: event.trigger.snapshot.price_move_5m,
      snapshot_liquidity: event.trigger.snapshot.liquidity,
      llm_verdict: event.verdict,
      llm_confidence: event.confidence,
      llm_reasoning: event.reasoning,
    };
    tracker.open(newSignal);
    deps.logger.info(`[executor] opened position ${newSignal.signal_id} size=$${fill.filledSize}`);
    return newSignal.signal_id;
  }

  async function onPriceTick(marketId: string, currentMidPrice: number, nowMs: number): Promise<void> {
    lastPriceMap.set(marketId, currentMidPrice);
    for (const pos of tracker.listOpen()) {
      if (pos.market_id !== marketId) continue;
      const decision = evaluateExit(pos, { currentPrice: currentMidPrice, nowMs }, deps.config, drawdownGuard);
      if (decision.exit && decision.reason) {
        await closePosition(pos, currentMidPrice, nowMs, decision.reason);
      }
    }
  }

  async function closePosition(
    pos: SignalLogRow,
    exitMidPrice: number,
    nowMs: number,
    reason: ExitReason
  ): Promise<void> {
    const fill = await deps.filler.fillSell({
      tokenId: pos.market_id,
      midPrice: exitMidPrice,
      sizeUsdc: pos.size_usdc,
      direction: pos.direction,
      timestampMs: nowMs,
    });

    if (!fill.filled) {
      deps.logger.warn(`[executor] sell fill failed for ${pos.signal_id}: ${fill.reason}`);
    }

    const exitPrice = fill.filled ? fill.fillPrice : exitMidPrice;
    const pnl = computePnL({
      direction: pos.direction,
      sizeUsdc: pos.size_usdc,
      entryPrice: pos.entry_price,
      exitPrice,
      feePct: 0,
      slippagePct: deps.config.paperSlippagePct,
      gasUsdc: deps.config.gasPerTradeUsdc,
    });
    tracker.close(pos.signal_id, {
      exit_at: nowMs,
      exit_price: exitPrice,
      exit_reason: reason,
      pnl_gross_usdc: pnl.pnlGross,
      fees_usdc: pnl.fees,
      slippage_usdc: pnl.slippage,
      gas_usdc: pnl.gas,
      pnl_net_usdc: pnl.pnlNet,
      holding_duration_sec: Math.floor((nowMs - pos.triggered_at) / 1000),
    });
    lock.release(pos.market_id);
    drawdownGuard.clear(pos.signal_id);

    const state = deps.portfolioRepo.read();
    deps.portfolioRepo.update({ current_equity: state.current_equity + pnl.pnlNet });
    breaker.evaluate();

    deps.logger.info(
      `[executor] closed ${pos.signal_id} reason=${reason} netPnl=$${pnl.pnlNet.toFixed(2)}`
    );
  }

  return {
    handleVerdict,
    onPriceTick,
    closePosition,
    openPositions: () => tracker.listOpen(),
    getLastPrice: (marketId) => lastPriceMap.get(marketId),
  };
}
