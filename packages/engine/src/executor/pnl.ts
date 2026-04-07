import type { Direction } from "../db/types.js";

export interface PnLInput {
  direction: Direction;
  sizeUsdc: number;
  entryPrice: number;
  exitPrice: number;
  feePct: number;
  slippagePct: number;
  gasUsdc: number;
}

export interface PnLResult {
  pnlGross: number;
  fees: number;
  slippage: number;
  gas: number;
  pnlNet: number;
}

export function computePnL(input: PnLInput): PnLResult {
  const { direction: _direction, sizeUsdc, entryPrice, exitPrice, feePct, slippagePct, gasUsdc } = input;
  void _direction;
  const shares = sizeUsdc / entryPrice;
  const exitValue = shares * exitPrice;
  const pnlGross = exitValue - sizeUsdc;
  const fees = sizeUsdc * feePct + exitValue * feePct;
  const slippage = sizeUsdc * slippagePct + exitValue * slippagePct;
  const gas = gasUsdc;
  const pnlNet = pnlGross - fees - slippage - gas;
  return { pnlGross, fees, slippage, gas, pnlNet };
}
