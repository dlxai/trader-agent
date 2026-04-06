import type { TriggerEvent, VerdictEvent, OrderRequestEvent, ExitRequestEvent } from "./types.js";

type Listener<E> = (event: E) => void | Promise<void>;
type Unsubscribe = () => void;

export interface EventBus {
  onTrigger(listener: Listener<TriggerEvent>): Unsubscribe;
  onVerdict(listener: Listener<VerdictEvent>): Unsubscribe;
  onOrderRequest(listener: Listener<OrderRequestEvent>): Unsubscribe;
  onExitRequest(listener: Listener<ExitRequestEvent>): Unsubscribe;
  publishTrigger(event: TriggerEvent): void;
  publishVerdict(event: VerdictEvent): void;
  publishOrderRequest(event: OrderRequestEvent): void;
  publishExitRequest(event: ExitRequestEvent): void;
}

export function createEventBus(): EventBus {
  const triggerListeners = new Set<Listener<TriggerEvent>>();
  const verdictListeners = new Set<Listener<VerdictEvent>>();
  const orderListeners = new Set<Listener<OrderRequestEvent>>();
  const exitListeners = new Set<Listener<ExitRequestEvent>>();

  function sub<E>(set: Set<Listener<E>>, listener: Listener<E>): Unsubscribe {
    set.add(listener);
    return () => set.delete(listener);
  }

  function pub<E>(set: Set<Listener<E>>, event: E): void {
    for (const listener of set) {
      try {
        const result = listener(event);
        if (result instanceof Promise) {
          result.catch((err) => {
            // Listeners are fire-and-forget; errors must not stop other listeners.
            // Log via console because this module has no api.logger access; the
            // plugin entry wraps this with a proper logger adapter at production time.
            // eslint-disable-next-line no-console
            console.error("[event-bus] async listener error:", err);
          });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[event-bus] sync listener error:", err);
      }
    }
  }

  return {
    onTrigger: (l) => sub(triggerListeners, l),
    onVerdict: (l) => sub(verdictListeners, l),
    onOrderRequest: (l) => sub(orderListeners, l),
    onExitRequest: (l) => sub(exitListeners, l),
    publishTrigger: (e) => pub(triggerListeners, e),
    publishVerdict: (e) => pub(verdictListeners, e),
    publishOrderRequest: (e) => pub(orderListeners, e),
    publishExitRequest: (e) => pub(exitListeners, e),
  };
}
