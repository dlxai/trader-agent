import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createCoordinatorScheduler } from "../src/coordinator.js";

describe("coordinatorScheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs at the configured interval", async () => {
    const generateBrief = vi.fn().mockResolvedValue({
      summary: "test",
      alerts: [],
      suggestions: [],
    });
    const onBrief = vi.fn();
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief,
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    expect(generateBrief).toHaveBeenCalledTimes(1);
    expect(onBrief).toHaveBeenCalledWith({
      summary: "test",
      alerts: [],
      suggestions: [],
    });
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000);
    expect(generateBrief).toHaveBeenCalledTimes(2);
  });

  it("does not call onBrief if generateBrief returns null", async () => {
    const generateBrief = vi.fn().mockResolvedValue(null);
    const onBrief = vi.fn();
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief,
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    expect(generateBrief).toHaveBeenCalledTimes(1);
    expect(onBrief).not.toHaveBeenCalled();
  });

  it("stop() halts further runs", async () => {
    const generateBrief = vi.fn().mockResolvedValue({ summary: "x", alerts: [], suggestions: [] });
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief: vi.fn(),
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    scheduler.stop();
    await vi.advanceTimersByTimeAsync(2 * 60 * 60 * 1000);
    expect(generateBrief).toHaveBeenCalledTimes(1);
  });
});
