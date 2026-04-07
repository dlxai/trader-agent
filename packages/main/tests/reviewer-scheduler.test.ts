import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createReviewerScheduler } from "../src/reviewer-scheduler.js";

describe("reviewerScheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("invokes reviewer on first start when never run before", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => null,
      onRun: vi.fn(),
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    expect(runReviewer).toHaveBeenCalledTimes(1);
  });

  it("waits 24 hours between runs after a successful run", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    let lastRun = Date.now();
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => lastRun,
      onRun: () => {
        lastRun = Date.now();
      },
    });
    scheduler.start();
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000); // 1 hour
    expect(runReviewer).toHaveBeenCalledTimes(0);
    await vi.advanceTimersByTimeAsync(23 * 60 * 60 * 1000); // 23 more hours = 24h total
    expect(runReviewer).toHaveBeenCalledTimes(1);
  });

  it("stop() clears the timer", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => Date.now(),
      onRun: vi.fn(),
    });
    scheduler.start();
    scheduler.stop();
    await vi.advanceTimersByTimeAsync(48 * 60 * 60 * 1000);
    expect(runReviewer).toHaveBeenCalledTimes(0);
  });
});
