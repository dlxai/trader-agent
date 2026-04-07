export type Direction = "buy_yes" | "buy_no";
export type ExitReason = "E" | "A_SL" | "A_TP" | "D" | "C";
export type LlmVerdict = "real_signal" | "noise" | "uncertain";

export interface SignalLogRow {
  signal_id: string;
  market_id: string;
  market_title: string;
  resolves_at: number;
  triggered_at: number;
  direction: Direction;
  entry_price: number;
  price_bucket: number;
  size_usdc: number;
  kelly_fraction: number;
  snapshot_volume_1m: number;
  snapshot_net_flow_1m: number;
  snapshot_unique_traders_1m: number;
  snapshot_price_move_5m: number;
  snapshot_liquidity: number;
  llm_verdict: LlmVerdict;
  llm_confidence: number;
  llm_reasoning: string;
  exit_at: number | null;
  exit_price: number | null;
  exit_reason: ExitReason | null;
  pnl_gross_usdc: number | null;
  fees_usdc: number | null;
  slippage_usdc: number | null;
  gas_usdc: number | null;
  pnl_net_usdc: number | null;
  holding_duration_sec: number | null;
}

export type NewSignal = Omit<
  SignalLogRow,
  | "exit_at"
  | "exit_price"
  | "exit_reason"
  | "pnl_gross_usdc"
  | "fees_usdc"
  | "slippage_usdc"
  | "gas_usdc"
  | "pnl_net_usdc"
  | "holding_duration_sec"
>;

export interface ExitFill {
  exit_at: number;
  exit_price: number;
  exit_reason: ExitReason;
  pnl_gross_usdc: number;
  fees_usdc: number;
  slippage_usdc: number;
  gas_usdc: number;
  pnl_net_usdc: number;
  holding_duration_sec: number;
}
