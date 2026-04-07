import type { Direction, LlmVerdict } from "../db/types.js";

export interface MarketSnapshot {
  volume_1m: number;
  net_flow_1m: number;
  unique_traders_1m: number;
  price_move_5m: number;
  liquidity: number;
  current_mid_price: number;
}

export interface TriggerEvent {
  type: "trigger";
  market_id: string;
  market_title: string;
  resolves_at: number;
  triggered_at: number;
  direction: Direction;
  snapshot: MarketSnapshot;
}

export interface VerdictEvent {
  type: "verdict";
  trigger: TriggerEvent;
  verdict: LlmVerdict;
  confidence: number;
  reasoning: string;
  llm_direction: Direction;
}

export interface OrderRequestEvent {
  type: "order_request";
  verdict: VerdictEvent;
}

export interface ExitRequestEvent {
  type: "exit_request";
  signal_id: string;
  reason: "E" | "A_SL" | "A_TP" | "D" | "C";
}

export type BusEvent = TriggerEvent | VerdictEvent | OrderRequestEvent | ExitRequestEvent;
