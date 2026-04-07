import { describe, it, expect, vi } from "vitest";
import { createAlertDispatcher } from "../../src/reviewer/alert-dispatcher.js";

describe("alertDispatcher", () => {
  it("dispatches critical alerts through the provided sender", async () => {
    const sender = vi.fn().mockResolvedValue(true);
    const dispatcher = createAlertDispatcher({
      sender,
      channel: "telegram",
      userId: "chat-123",
    });
    await dispatcher.dispatch({
      severity: "critical",
      title: "Kill switch fired",
      body: "smart_money_flow killed (win rate 30%)",
    });
    expect(sender).toHaveBeenCalledWith(
      "telegram",
      "chat-123",
      expect.stringContaining("Kill switch fired")
    );
  });

  it("silently drops alerts when no channel configured", async () => {
    const sender = vi.fn();
    const dispatcher = createAlertDispatcher({ sender, channel: null, userId: null });
    await dispatcher.dispatch({ severity: "info", title: "t", body: "b" });
    expect(sender).not.toHaveBeenCalled();
  });
});
