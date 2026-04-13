import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createPositionEvaluatorLoop } from "../../src/executor/position-evaluator.js";

describe("PositionEvaluatorLoop", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("calls evaluator on interval when positions exist", async () => {
    const evaluateFn = vi.fn().mockResolvedValue({ positions: [{ signal_id: "s1", action: "hold", reasoning: "ok" }] });
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);
    const onAction = vi.fn();

    const loop = createPositionEvaluatorLoop({ intervalSec: 10, getOpenPositions: getPositions, evaluate: evaluateFn, onAction });
    loop.start();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(evaluateFn).toHaveBeenCalledTimes(1);
    expect(onAction).not.toHaveBeenCalled(); // hold = no action
    loop.stop();
  });

  it("calls onAction for close decisions", async () => {
    const evaluateFn = vi.fn().mockResolvedValue({ positions: [{ signal_id: "s1", action: "close", reasoning: "bad" }] });
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);
    const onAction = vi.fn();

    const loop = createPositionEvaluatorLoop({ intervalSec: 10, getOpenPositions: getPositions, evaluate: evaluateFn, onAction });
    loop.start();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ signal_id: "s1", action: "close" }));
    loop.stop();
  });

  it("skips when no open positions", async () => {
    const evaluateFn = vi.fn();
    const getPositions = vi.fn().mockReturnValue([]);

    const loop = createPositionEvaluatorLoop({ intervalSec: 10, getOpenPositions: getPositions, evaluate: evaluateFn, onAction: vi.fn() });
    loop.start();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(evaluateFn).not.toHaveBeenCalled();
    loop.stop();
  });

  it("triggerNow runs immediately", async () => {
    const evaluateFn = vi.fn().mockResolvedValue({ positions: [] });
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);

    const loop = createPositionEvaluatorLoop({ intervalSec: 999, getOpenPositions: getPositions, evaluate: evaluateFn, onAction: vi.fn() });
    await loop.triggerNow();
    expect(evaluateFn).toHaveBeenCalledTimes(1);
  });

  it("handles evaluate returning null gracefully", async () => {
    const evaluateFn = vi.fn().mockResolvedValue(null);
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);
    const onAction = vi.fn();

    const loop = createPositionEvaluatorLoop({ intervalSec: 10, getOpenPositions: getPositions, evaluate: evaluateFn, onAction });
    loop.start();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(onAction).not.toHaveBeenCalled();
    loop.stop();
  });
});
