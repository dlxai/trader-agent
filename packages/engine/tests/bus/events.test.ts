import { describe, it, expect, vi } from "vitest";
import { createEventBus } from "../../src/bus/events.js";
import type { TriggerEvent } from "../../src/bus/types.js";

const sampleTrigger: TriggerEvent = {
  type: "trigger",
  market_id: "m1",
  market_title: "Test",
  resolves_at: Date.now() + 3_600_000,
  triggered_at: Date.now(),
  direction: "buy_yes",
  snapshot: {
    volume_1m: 3500,
    net_flow_1m: 3200,
    unique_traders_1m: 4,
    price_move_5m: 0.04,
    liquidity: 6000,
    current_mid_price: 0.55,
  },
};

describe("createEventBus", () => {
  it("delivers published trigger to subscribed listener", () => {
    const bus = createEventBus();
    const listener = vi.fn();
    bus.onTrigger(listener);
    bus.publishTrigger(sampleTrigger);
    expect(listener).toHaveBeenCalledWith(sampleTrigger);
  });

  it("supports multiple listeners for same event", () => {
    const bus = createEventBus();
    const a = vi.fn();
    const b = vi.fn();
    bus.onTrigger(a);
    bus.onTrigger(b);
    bus.publishTrigger(sampleTrigger);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("unsubscribe stops future deliveries", () => {
    const bus = createEventBus();
    const listener = vi.fn();
    const off = bus.onTrigger(listener);
    off();
    bus.publishTrigger(sampleTrigger);
    expect(listener).not.toHaveBeenCalled();
  });

  it("does not cross-deliver between event types", () => {
    const bus = createEventBus();
    const triggerListener = vi.fn();
    const exitListener = vi.fn();
    bus.onTrigger(triggerListener);
    bus.onExitRequest(exitListener);
    bus.publishTrigger(sampleTrigger);
    expect(exitListener).not.toHaveBeenCalled();
  });
});
