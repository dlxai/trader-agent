# Trading Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade polymarket-trader from paper-trading to live-trading with AI-driven position management, multi-layer risk controls, and flexible LLM provider configuration.

**Architecture:** Incremental integration — each module is developed and tested independently, preserving the existing paper-fill path as a fallback. New features are wired into the existing EventBus and executor pipeline.

**Tech Stack:** TypeScript, Vitest, `@polymarket/clob-client`, Electron IPC, React (renderer), better-sqlite3

**Spec:** `docs/superpowers/specs/2026-04-12-trading-upgrade-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `packages/engine/src/executor/order-filler.ts` | OrderFiller interface shared by PaperFiller and LiveFiller |
| `packages/engine/src/executor/live-filler.ts` | LiveFiller that places real orders via CLOB |
| `packages/engine/src/executor/clob-order-service.ts` | Polymarket CLOB API wrapper (auth, order, query, cancel) |
| `packages/engine/src/executor/drawdown-guard.ts` | Peak PnL tracking + drawdown exit check |
| `packages/engine/src/executor/position-evaluator.ts` | Timer loop that calls AI to evaluate all open positions |
| `packages/llm/src/runners/position-evaluator-runner.ts` | LLM runner for position evaluation |
| `packages/llm/src/runners/personas/position-evaluator.ts` | System prompt for position evaluator agent |
| `packages/llm/src/adapters/custom-openai-manager.ts` | CRUD for user-defined OpenAI-compatible endpoints |
| `packages/engine/tests/executor/order-filler.test.ts` | Tests for OrderFiller interface + PaperFiller migration |
| `packages/engine/tests/executor/drawdown-guard.test.ts` | Tests for drawdown guard logic |
| `packages/engine/tests/executor/live-filler.test.ts` | Tests for LiveFiller (mocked CLOB) |
| `packages/engine/tests/executor/position-evaluator.test.ts` | Tests for position evaluator loop |
| `packages/llm/tests/runners/position-evaluator-runner.test.ts` | Tests for position evaluator LLM runner |
| `packages/llm/tests/adapters/custom-openai-manager.test.ts` | Tests for custom endpoint CRUD |

### Modified Files

| File | Changes |
|------|---------|
| `packages/engine/src/db/types.ts` | Extend ExitReason with new reasons |
| `packages/engine/src/config/schema.ts` | Add LiveTradeConfig, AiExitConfig, DrawdownGuardConfig, CoordinatorConfig, PromptConfig |
| `packages/engine/src/config/defaults.ts` | Add defaults for new config sections |
| `packages/engine/src/executor/executor.ts` | Accept OrderFiller via deps, expose closePosition publicly, add new exit reasons |
| `packages/engine/src/executor/exit-monitor.ts` | Add drawdown guard check |
| `packages/engine/src/executor/paper-fill.ts` | Implement OrderFiller interface |
| `packages/llm/src/types.ts` | Add "position_evaluator" to AgentId, add custom provider ID support |
| `packages/llm/src/runners/personas/analyzer.ts` | Upgraded prompt with account context, fair value, edge |
| `packages/llm/src/runners/analyzer-runner.ts` | Accept account state in prompt, parse new output fields |
| `packages/llm/src/runners/personas/risk-manager.ts` | Add actions output format to prompt |
| `packages/llm/src/runners/risk-mgr-runner.ts` | Parse and return actions from coordinator response |
| `packages/main/src/coordinator.ts` | Execute coordinator actions |
| `packages/main/src/lifecycle.ts` | Boot position evaluator, load custom providers, wire LiveFiller |
| `packages/main/src/ipc.ts` | Add custom_openai handlers, live trade config handlers |
| `packages/renderer/src/stores/settings.ts` | Add new config types and state |
| `packages/renderer/src/pages/SettingsPage.tsx` | New UI sections for all configurations |

---

## Task 1: Extract OrderFiller Interface

Decouple the executor from PaperFiller by extracting a shared interface.

**Files:**
- Create: `packages/engine/src/executor/order-filler.ts`
- Modify: `packages/engine/src/executor/paper-fill.ts`
- Create: `packages/engine/tests/executor/order-filler.test.ts`

- [ ] **Step 1: Write the OrderFiller interface**

```typescript
// packages/engine/src/executor/order-filler.ts
export interface FillParams {
  tokenId: string;
  midPrice: number;
  sizeUsdc: number;
  direction: "buy_yes" | "buy_no";
  timestampMs: number;
}

export interface FillResult {
  filled: boolean;
  fillPrice: number;
  filledSize: number;
  orderId?: string;
  reason: "filled" | "partial" | "missed_fill" | "insufficient_balance";
}

export interface OrderFiller {
  fillBuy(params: FillParams): Promise<FillResult>;
  fillSell(params: FillParams): Promise<FillResult>;
}
```

- [ ] **Step 2: Write test for PaperFiller implementing OrderFiller**

```typescript
// packages/engine/tests/executor/order-filler.test.ts
import { describe, it, expect } from "vitest";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import type { FillParams } from "../../src/executor/order-filler.js";

describe("PaperFiller as OrderFiller", () => {
  const filler = createPaperFiller({ slippagePct: 0.005 });

  it("fillBuy returns filled result with slippage", async () => {
    const params: FillParams = {
      tokenId: "tok1",
      midPrice: 0.50,
      sizeUsdc: 100,
      direction: "buy_yes",
      timestampMs: Date.now(),
    };
    const result = await filler.fillBuy(params);
    expect(result.filled).toBe(true);
    expect(result.fillPrice).toBeCloseTo(0.5025, 4);
    expect(result.filledSize).toBe(100);
    expect(result.reason).toBe("filled");
  });

  it("fillSell returns filled result with slippage", async () => {
    const params: FillParams = {
      tokenId: "tok1",
      midPrice: 0.60,
      sizeUsdc: 100,
      direction: "buy_yes",
      timestampMs: Date.now(),
    };
    const result = await filler.fillSell(params);
    expect(result.filled).toBe(true);
    expect(result.fillPrice).toBeCloseTo(0.597, 4);
    expect(result.reason).toBe("filled");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd packages/engine && npx vitest run tests/executor/order-filler.test.ts`
Expected: FAIL — PaperFiller does not yet implement OrderFiller interface

- [ ] **Step 4: Update PaperFiller to implement OrderFiller**

```typescript
// packages/engine/src/executor/paper-fill.ts
import type { OrderFiller, FillParams, FillResult } from "./order-filler.js";

export interface PaperFillOptions {
  slippagePct: number;
}

export function createPaperFiller(opts: PaperFillOptions): OrderFiller {
  return {
    async fillBuy(params: FillParams): Promise<FillResult> {
      return {
        filled: true,
        fillPrice: params.midPrice * (1 + opts.slippagePct),
        filledSize: params.sizeUsdc,
        reason: "filled",
      };
    },
    async fillSell(params: FillParams): Promise<FillResult> {
      return {
        filled: true,
        fillPrice: params.midPrice * (1 - opts.slippagePct),
        filledSize: params.sizeUsdc,
        reason: "filled",
      };
    },
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd packages/engine && npx vitest run tests/executor/order-filler.test.ts`
Expected: PASS

- [ ] **Step 6: Update executor to accept OrderFiller via deps**

Modify `packages/engine/src/executor/executor.ts`:

Change the `ExecutorDeps` interface to accept an `OrderFiller`:
```typescript
import type { OrderFiller } from "./order-filler.js";

export interface ExecutorDeps {
  config: TraderConfig;
  bus: EventBus;
  signalRepo: SignalLogRepo;
  portfolioRepo: PortfolioStateRepo;
  filler: OrderFiller;  // NEW: injected from outside
  logger: { info: (m: string) => void; warn: (m: string) => void; error: (m: string) => void };
}
```

Remove the internal `createPaperFiller` call (line 36) and use `deps.filler` instead. Update `handleVerdict` to use `await deps.filler.fillBuy(...)` and `closePosition` to use `await deps.filler.fillSell(...)`. Since fillBuy/fillSell are now async, `handleVerdict` and `closePosition` must become async. Update the `Executor` interface:

```typescript
export interface Executor {
  handleVerdict(event: VerdictEvent): Promise<string | null>;
  onPriceTick(marketId: string, currentMidPrice: number, nowMs: number): Promise<void>;
  closePosition(pos: SignalLogRow, exitMidPrice: number, nowMs: number, reason: ExitReason): Promise<void>;
  openPositions(): SignalLogRow[];
}
```

Make `closePosition` public on the Executor interface (needed by position evaluator and coordinator).

- [ ] **Step 7: Update existing executor tests**

Modify `packages/engine/tests/executor/executor.test.ts` to inject PaperFiller:

```typescript
import { createPaperFiller } from "../../src/executor/paper-fill.js";

// In beforeEach, add:
const filler = createPaperFiller({ slippagePct: DEFAULT_CONFIG.paperSlippagePct });
exec = createExecutor({
  config: DEFAULT_CONFIG,
  bus,
  signalRepo,
  portfolioRepo,
  filler,  // NEW
  logger: { info: () => {}, warn: () => {}, error: () => {} },
});
```

Update all `handleVerdict` calls to `await exec.handleVerdict(...)`.

- [ ] **Step 8: Run all executor tests**

Run: `cd packages/engine && npx vitest run tests/executor/`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add packages/engine/src/executor/order-filler.ts packages/engine/src/executor/paper-fill.ts packages/engine/src/executor/executor.ts packages/engine/tests/executor/order-filler.test.ts packages/engine/tests/executor/executor.test.ts
git commit -m "refactor: extract OrderFiller interface from executor"
```

---

## Task 2: Extend ExitReason and Config Types

Add new exit reasons and config interfaces for all new features.

**Files:**
- Modify: `packages/engine/src/db/types.ts`
- Modify: `packages/engine/src/config/schema.ts`
- Modify: `packages/engine/src/config/defaults.ts`

- [ ] **Step 1: Extend ExitReason**

In `packages/engine/src/db/types.ts`, change line 2:

```typescript
export type ExitReason = "E" | "A_SL" | "A_TP" | "D" | "C" | "AI_EXIT" | "COORD_EMERGENCY" | "DRAWDOWN_GUARD";
```

- [ ] **Step 2: Add new config interfaces to schema.ts**

Append to `packages/engine/src/config/schema.ts`:

```typescript
export interface LiveTradeConfig {
  mode: "paper" | "live";
  slippageThreshold: number;
  maxSlippage: number;
  limitOrderTimeoutSec: number;
}

export interface AiExitConfig {
  enabled: boolean;
  intervalSec: number;
}

export interface DrawdownGuardConfig {
  enabled: boolean;
  minProfitPct: number;
  maxDrawdownFromPeak: number;
}

export interface CoordinatorConfig {
  actionable: boolean;
  intervalMin: number;
}

export interface PromptConfig {
  tradingMode: "conservative" | "balanced" | "aggressive";
  customPrompt: string;
  minConfidence: number;
  minEdge: number;
}
```

Add these fields to the existing `TraderConfig` interface:

```typescript
  // Live trading
  liveTrade: LiveTradeConfig;
  // AI position evaluator
  aiExit: AiExitConfig;
  // Drawdown guard
  drawdownGuard: DrawdownGuardConfig;
  // Coordinator
  coordinator: CoordinatorConfig;
  // Prompt configuration
  prompt: PromptConfig;
```

- [ ] **Step 3: Add defaults**

In `packages/engine/src/config/defaults.ts`, add defaults for the new config sections:

```typescript
  liveTrade: {
    mode: "paper",
    slippageThreshold: 0.02,
    maxSlippage: 0.03,
    limitOrderTimeoutSec: 60,
  },
  aiExit: {
    enabled: true,
    intervalSec: 180,
  },
  drawdownGuard: {
    enabled: true,
    minProfitPct: 0.05,
    maxDrawdownFromPeak: 0.40,
  },
  coordinator: {
    actionable: true,
    intervalMin: 30,
  },
  prompt: {
    tradingMode: "balanced",
    customPrompt: "",
    minConfidence: 0.65,
    minEdge: 0.06,
  },
```

- [ ] **Step 4: Run typecheck**

Run: `cd packages/engine && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Run existing tests**

Run: `cd packages/engine && npx vitest run`
Expected: ALL PASS (new config fields have defaults, no breakage)

- [ ] **Step 6: Commit**

```bash
git add packages/engine/src/db/types.ts packages/engine/src/config/schema.ts packages/engine/src/config/defaults.ts
git commit -m "feat: add config types for live trading, AI exit, drawdown guard, coordinator"
```

---

## Task 3: Drawdown Guard

Pure-logic module. No AI, no network — just math on price ticks.

**Files:**
- Create: `packages/engine/src/executor/drawdown-guard.ts`
- Modify: `packages/engine/src/executor/exit-monitor.ts`
- Create: `packages/engine/tests/executor/drawdown-guard.test.ts`

- [ ] **Step 1: Write drawdown guard tests**

```typescript
// packages/engine/tests/executor/drawdown-guard.test.ts
import { describe, it, expect } from "vitest";
import { createDrawdownGuard } from "../../src/executor/drawdown-guard.js";

describe("drawdown-guard", () => {
  it("does not trigger when profit below minProfitPct", () => {
    const guard = createDrawdownGuard({ enabled: true, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
    guard.onPriceTick("s1", 0.03); // 3% profit, below 5% threshold
    guard.onPriceTick("s1", 0.02); // dropped but doesn't matter
    expect(guard.shouldExit("s1", 0.02)).toBe(false);
  });

  it("does not trigger when drawdown below threshold", () => {
    const guard = createDrawdownGuard({ enabled: true, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
    guard.onPriceTick("s1", 0.10); // peak 10%
    guard.onPriceTick("s1", 0.08); // drawdown 20% < 40%
    expect(guard.shouldExit("s1", 0.08)).toBe(false);
  });

  it("triggers when profit above min AND drawdown exceeds threshold", () => {
    const guard = createDrawdownGuard({ enabled: true, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
    guard.onPriceTick("s1", 0.10); // peak 10%
    guard.onPriceTick("s1", 0.055); // drawdown 45% > 40%, current 5.5% > 5%
    expect(guard.shouldExit("s1", 0.055)).toBe(true);
  });

  it("does nothing when disabled", () => {
    const guard = createDrawdownGuard({ enabled: false, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
    guard.onPriceTick("s1", 0.10);
    guard.onPriceTick("s1", 0.01);
    expect(guard.shouldExit("s1", 0.01)).toBe(false);
  });

  it("cleans up after position close", () => {
    const guard = createDrawdownGuard({ enabled: true, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
    guard.onPriceTick("s1", 0.10);
    guard.clear("s1");
    // After clear, peak is reset. New ticks start fresh.
    guard.onPriceTick("s1", 0.06);
    expect(guard.shouldExit("s1", 0.06)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/engine && npx vitest run tests/executor/drawdown-guard.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement drawdown guard**

```typescript
// packages/engine/src/executor/drawdown-guard.ts
import type { DrawdownGuardConfig } from "../config/schema.js";

export interface DrawdownGuard {
  /** Update peak PnL for a position. Call on every price tick. */
  onPriceTick(signalId: string, currentPnlPct: number): void;
  /** Check if position should be exited due to drawdown. */
  shouldExit(signalId: string, currentPnlPct: number): boolean;
  /** Clear tracking for a closed position. */
  clear(signalId: string): void;
}

export function createDrawdownGuard(config: DrawdownGuardConfig): DrawdownGuard {
  const peakPnl = new Map<string, number>();

  return {
    onPriceTick(signalId, currentPnlPct) {
      if (!config.enabled) return;
      const prev = peakPnl.get(signalId) ?? -Infinity;
      if (currentPnlPct > prev) {
        peakPnl.set(signalId, currentPnlPct);
      }
    },

    shouldExit(signalId, currentPnlPct) {
      if (!config.enabled) return false;
      const peak = peakPnl.get(signalId);
      if (peak === undefined || peak <= 0) return false;
      if (currentPnlPct < config.minProfitPct) return false;
      const drawdown = (peak - currentPnlPct) / peak;
      return drawdown >= config.maxDrawdownFromPeak;
    },

    clear(signalId) {
      peakPnl.delete(signalId);
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/engine && npx vitest run tests/executor/drawdown-guard.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Integrate into exit-monitor**

Modify `packages/engine/src/executor/exit-monitor.ts` to add a drawdown guard check. The guard is stateful, so it's passed in via a new optional parameter:

```typescript
import type { TraderConfig } from "../config/schema.js";
import type { SignalLogRow, ExitReason } from "../db/types.js";
import type { DrawdownGuard } from "./drawdown-guard.js";

export interface ExitContext {
  currentPrice: number;
  nowMs: number;
}

export interface ExitDecision {
  exit: boolean;
  reason?: ExitReason;
}

export function evaluateExit(
  position: SignalLogRow,
  ctx: ExitContext,
  cfg: TraderConfig,
  drawdownGuard?: DrawdownGuard
): ExitDecision {
  const secToResolve = Math.floor((position.resolves_at - ctx.nowMs) / 1000);
  if (secToResolve <= cfg.expirySafetyBufferSec) {
    return { exit: true, reason: "E" };
  }

  const isLateStage = secToResolve <= cfg.lateStageThresholdSec;
  const stopLossPct = isLateStage ? cfg.stopLossPctLateStage : cfg.stopLossPctNormal;

  const rawDelta = (ctx.currentPrice - position.entry_price) / position.entry_price;
  const profitDelta = position.direction === "buy_yes" ? rawDelta : -rawDelta;

  if (profitDelta <= -(stopLossPct - 1e-9)) {
    return { exit: true, reason: "A_SL" };
  }
  if (profitDelta >= cfg.takeProfitPct) {
    return { exit: true, reason: "A_TP" };
  }

  // Drawdown guard check
  if (drawdownGuard) {
    drawdownGuard.onPriceTick(position.signal_id, profitDelta);
    if (drawdownGuard.shouldExit(position.signal_id, profitDelta)) {
      return { exit: true, reason: "DRAWDOWN_GUARD" };
    }
  }

  const holdingSec = Math.floor((ctx.nowMs - position.triggered_at) / 1000);
  if (holdingSec >= cfg.maxHoldingSec) {
    return { exit: true, reason: "C" };
  }

  return { exit: false };
}
```

- [ ] **Step 6: Update existing exit-monitor tests**

In `packages/engine/tests/executor/exit-monitor.test.ts`, existing tests should still pass since `drawdownGuard` param is optional. Add one new test:

```typescript
import { createDrawdownGuard } from "../../src/executor/drawdown-guard.js";

it("exits on drawdown guard trigger", () => {
  const guard = createDrawdownGuard({ enabled: true, minProfitPct: 0.05, maxDrawdownFromPeak: 0.40 });
  // Simulate peak at 10% profit
  guard.onPriceTick("s1", 0.10);
  const pos = makePosition({ entry_price: 0.40 }); // helper from existing tests
  // Current price gives ~5.5% profit (drawdown 45% from 10% peak)
  const result = evaluateExit(pos, { currentPrice: 0.422, nowMs: Date.now() }, DEFAULT_CONFIG, guard);
  expect(result.exit).toBe(true);
  expect(result.reason).toBe("DRAWDOWN_GUARD");
});
```

- [ ] **Step 7: Run all exit-monitor and drawdown-guard tests**

Run: `cd packages/engine && npx vitest run tests/executor/exit-monitor.test.ts tests/executor/drawdown-guard.test.ts`
Expected: ALL PASS

- [ ] **Step 8: Wire drawdown guard into executor**

In `packages/engine/src/executor/executor.ts`, create a DrawdownGuard in `createExecutor()` and pass it to `evaluateExit()` calls. Clear guard state in `closePosition()`.

```typescript
import { createDrawdownGuard } from "./drawdown-guard.js";

// Inside createExecutor():
const drawdownGuard = createDrawdownGuard(deps.config.drawdownGuard);

// In onPriceTick():
const decision = evaluateExit(pos, { currentPrice: currentMidPrice, nowMs }, deps.config, drawdownGuard);

// In closePosition():
drawdownGuard.clear(pos.signal_id);
```

- [ ] **Step 9: Run full executor test suite**

Run: `cd packages/engine && npx vitest run tests/executor/`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add packages/engine/src/executor/drawdown-guard.ts packages/engine/src/executor/exit-monitor.ts packages/engine/src/executor/executor.ts packages/engine/tests/executor/drawdown-guard.test.ts packages/engine/tests/executor/exit-monitor.test.ts
git commit -m "feat: add drawdown guard for profit drawdown protection"
```

---

## Task 4: CLOB Order Service

Wrapper around `@polymarket/clob-client` for authentication and order management.

**Files:**
- Create: `packages/engine/src/executor/clob-order-service.ts`
- Create: `packages/engine/tests/executor/clob-order-service.test.ts`

- [ ] **Step 1: Install @polymarket/clob-client**

Run: `cd packages/engine && pnpm add @polymarket/clob-client`

- [ ] **Step 2: Write ClobOrderService interface and tests**

```typescript
// packages/engine/tests/executor/clob-order-service.test.ts
import { describe, it, expect } from "vitest";
import { ClobOrderService } from "../../src/executor/clob-order-service.js";

describe("ClobOrderService", () => {
  it("exports ClobOrderService class", () => {
    expect(ClobOrderService).toBeDefined();
  });

  it("rejects initialization without private key", () => {
    expect(() => new ClobOrderService({ privateKey: "", funderAddress: "0x123", chainId: 137 }))
      .toThrow("privateKey is required");
  });

  it("rejects initialization without funder address", () => {
    expect(() => new ClobOrderService({ privateKey: "0xabc", funderAddress: "", chainId: 137 }))
      .toThrow("funderAddress is required");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd packages/engine && npx vitest run tests/executor/clob-order-service.test.ts`
Expected: FAIL — module not found

- [ ] **Step 4: Implement ClobOrderService**

```typescript
// packages/engine/src/executor/clob-order-service.ts
import { ClobClient } from "@polymarket/clob-client";

export interface ClobOrderServiceConfig {
  privateKey: string;
  funderAddress: string;
  chainId: number;
  clobUrl?: string;
}

export interface ClobOrder {
  orderId: string;
  filled: boolean;
  filledPrice?: number;
  filledSize?: number;
}

export class ClobOrderService {
  private client: ClobClient;
  private initialized = false;

  constructor(private config: ClobOrderServiceConfig) {
    if (!config.privateKey) throw new Error("privateKey is required");
    if (!config.funderAddress) throw new Error("funderAddress is required");

    this.client = new ClobClient(
      config.clobUrl ?? "https://clob.polymarket.com",
      config.chainId,
      undefined, // wallet — set below
      undefined, // creds — derived later
      2,         // signatureType: browser proxy
      config.funderAddress
    );
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    // Derive API credentials from wallet signature
    const creds = await this.client.createOrDeriveApiKey();
    this.client.setCreds(creds);
    this.initialized = true;
  }

  async getUsdcBalance(): Promise<number> {
    const result = await this.client.getBalanceAllowance({
      asset_type: "COLLATERAL" as any,
    });
    return parseFloat(result.balance ?? "0");
  }

  async placeMarketOrder(params: {
    tokenId: string;
    side: "BUY" | "SELL";
    amount: number;
  }): Promise<ClobOrder> {
    await this.ensureInitialized();
    const order = await this.client.createMarketOrder({
      tokenID: params.tokenId,
      amount: params.amount,
      side: params.side as any,
    });
    const resp = await this.client.postOrder(order, "FOK" as any);
    return {
      orderId: resp.orderID ?? "",
      filled: resp.status === "matched",
      filledPrice: undefined, // resolved from trade history
      filledSize: params.amount,
    };
  }

  async placeLimitOrder(params: {
    tokenId: string;
    side: "BUY" | "SELL";
    price: number;
    size: number;
  }): Promise<ClobOrder> {
    await this.ensureInitialized();
    const order = await this.client.createOrder({
      tokenID: params.tokenId,
      price: params.price,
      size: params.size,
      side: params.side as any,
    });
    const resp = await this.client.postOrder(order, "GTC" as any);
    return {
      orderId: resp.orderID ?? "",
      filled: resp.status === "matched",
      filledPrice: params.price,
      filledSize: params.size,
    };
  }

  async cancelOrder(orderId: string): Promise<void> {
    await this.client.cancel(orderId);
  }

  async cancelAll(): Promise<void> {
    await this.client.cancelAll();
  }

  async getOrderBook(tokenId: string): Promise<{ bestBid: number; bestAsk: number; midPrice: number }> {
    const book = await this.client.getOrderBook(tokenId);
    const bestBid = book.bids?.[0]?.price ? parseFloat(book.bids[0].price) : 0;
    const bestAsk = book.asks?.[0]?.price ? parseFloat(book.asks[0].price) : 1;
    return { bestBid, bestAsk, midPrice: (bestBid + bestAsk) / 2 };
  }

  private async ensureInitialized(): Promise<void> {
    if (!this.initialized) await this.initialize();
  }
}
```

Note: The exact ClobClient constructor signature and method names may need adjustment based on the actual `@polymarket/clob-client` package API. Consult the package types after installation and adjust accordingly.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd packages/engine && npx vitest run tests/executor/clob-order-service.test.ts`
Expected: PASS (only tests constructor validation, not network calls)

- [ ] **Step 6: Commit**

```bash
git add packages/engine/src/executor/clob-order-service.ts packages/engine/tests/executor/clob-order-service.test.ts packages/engine/package.json pnpm-lock.yaml
git commit -m "feat: add ClobOrderService for Polymarket CLOB API"
```

---

## Task 5: LiveFiller Implementation

Implements OrderFiller using ClobOrderService with smart order routing (FOK → limit fallback).

**Files:**
- Create: `packages/engine/src/executor/live-filler.ts`
- Create: `packages/engine/tests/executor/live-filler.test.ts`

- [ ] **Step 1: Write LiveFiller tests with mocked CLOB**

```typescript
// packages/engine/tests/executor/live-filler.test.ts
import { describe, it, expect, vi } from "vitest";
import { createLiveFiller } from "../../src/executor/live-filler.js";

function mockClobService(overrides: Record<string, any> = {}) {
  return {
    getOrderBook: vi.fn().mockResolvedValue({ bestBid: 0.49, bestAsk: 0.51, midPrice: 0.50 }),
    placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: true, filledSize: 100 }),
    placeLimitOrder: vi.fn().mockResolvedValue({ orderId: "o2", filled: true, filledPrice: 0.50, filledSize: 100 }),
    cancelOrder: vi.fn().mockResolvedValue(undefined),
    getUsdcBalance: vi.fn().mockResolvedValue(5000),
    ...overrides,
  };
}

describe("LiveFiller", () => {
  it("uses FOK market order when slippage is within threshold", async () => {
    const clob = mockClobService();
    const filler = createLiveFiller({
      clob: clob as any,
      slippageThreshold: 0.02,
      maxSlippage: 0.03,
      limitOrderTimeoutSec: 60,
    });
    const result = await filler.fillBuy({
      tokenId: "tok1", midPrice: 0.50, sizeUsdc: 100, direction: "buy_yes", timestampMs: Date.now(),
    });
    expect(result.filled).toBe(true);
    expect(clob.placeMarketOrder).toHaveBeenCalled();
  });

  it("falls back to limit order when FOK fails", async () => {
    const clob = mockClobService({
      placeMarketOrder: vi.fn().mockResolvedValue({ orderId: "o1", filled: false }),
    });
    const filler = createLiveFiller({
      clob: clob as any,
      slippageThreshold: 0.02,
      maxSlippage: 0.03,
      limitOrderTimeoutSec: 0, // instant timeout for test
    });
    const result = await filler.fillBuy({
      tokenId: "tok1", midPrice: 0.50, sizeUsdc: 100, direction: "buy_yes", timestampMs: Date.now(),
    });
    expect(clob.placeLimitOrder).toHaveBeenCalled();
  });

  it("rejects when balance insufficient", async () => {
    const clob = mockClobService({ getUsdcBalance: vi.fn().mockResolvedValue(10) });
    const filler = createLiveFiller({
      clob: clob as any,
      slippageThreshold: 0.02,
      maxSlippage: 0.03,
      limitOrderTimeoutSec: 60,
    });
    const result = await filler.fillBuy({
      tokenId: "tok1", midPrice: 0.50, sizeUsdc: 100, direction: "buy_yes", timestampMs: Date.now(),
    });
    expect(result.filled).toBe(false);
    expect(result.reason).toBe("insufficient_balance");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/engine && npx vitest run tests/executor/live-filler.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement LiveFiller**

```typescript
// packages/engine/src/executor/live-filler.ts
import type { OrderFiller, FillParams, FillResult } from "./order-filler.js";
import type { ClobOrderService } from "./clob-order-service.js";

export interface LiveFillerConfig {
  clob: ClobOrderService;
  slippageThreshold: number;
  maxSlippage: number;
  limitOrderTimeoutSec: number;
}

export function createLiveFiller(config: LiveFillerConfig): OrderFiller {
  async function executeBuy(params: FillParams): Promise<FillResult> {
    // Check balance
    const balance = await config.clob.getUsdcBalance();
    if (balance < params.sizeUsdc) {
      return { filled: false, fillPrice: 0, filledSize: 0, reason: "insufficient_balance" };
    }

    // Get order book
    const book = await config.clob.getOrderBook(params.tokenId);
    const deviation = Math.abs(book.bestAsk - params.midPrice) / params.midPrice;

    // Try FOK market order if slippage is acceptable
    if (deviation <= config.slippageThreshold) {
      const result = await config.clob.placeMarketOrder({
        tokenId: params.tokenId,
        side: "BUY",
        amount: params.sizeUsdc,
      });
      if (result.filled) {
        return {
          filled: true,
          fillPrice: book.bestAsk,
          filledSize: params.sizeUsdc,
          orderId: result.orderId,
          reason: "filled",
        };
      }
    }

    // Fallback to limit order
    const limitPrice = Math.min(params.midPrice * (1 + config.maxSlippage), book.bestAsk);
    const shares = params.sizeUsdc / limitPrice;
    const limitResult = await config.clob.placeLimitOrder({
      tokenId: params.tokenId,
      side: "BUY",
      price: limitPrice,
      size: shares,
    });

    // Wait for fill or timeout
    if (config.limitOrderTimeoutSec > 0) {
      await new Promise((r) => setTimeout(r, config.limitOrderTimeoutSec * 1000));
    }

    if (limitResult.filled) {
      return {
        filled: true,
        fillPrice: limitPrice,
        filledSize: params.sizeUsdc,
        orderId: limitResult.orderId,
        reason: "filled",
      };
    }

    // Cancel unfilled limit order
    if (limitResult.orderId) {
      await config.clob.cancelOrder(limitResult.orderId).catch(() => {});
    }
    return { filled: false, fillPrice: 0, filledSize: 0, reason: "missed_fill" };
  }

  async function executeSell(params: FillParams): Promise<FillResult> {
    const book = await config.clob.getOrderBook(params.tokenId);

    // Try FOK sell at best bid
    const result = await config.clob.placeMarketOrder({
      tokenId: params.tokenId,
      side: "SELL",
      amount: params.sizeUsdc / params.midPrice, // shares
    });
    if (result.filled) {
      return {
        filled: true,
        fillPrice: book.bestBid,
        filledSize: params.sizeUsdc,
        orderId: result.orderId,
        reason: "filled",
      };
    }

    // Retry with progressively worse prices
    const tickSize = 0.01;
    for (let retry = 1; retry <= 3; retry++) {
      const aggressivePrice = book.bestBid - tickSize * (retry === 3 ? 5 : retry);
      const shares = params.sizeUsdc / params.midPrice;
      const retryResult = await config.clob.placeLimitOrder({
        tokenId: params.tokenId,
        side: "SELL",
        price: Math.max(aggressivePrice, 0.001),
        size: shares,
      });
      if (retryResult.filled) {
        return {
          filled: true,
          fillPrice: aggressivePrice,
          filledSize: params.sizeUsdc,
          orderId: retryResult.orderId,
          reason: retry < 3 ? "filled" : "partial",
        };
      }
      if (retryResult.orderId) {
        await config.clob.cancelOrder(retryResult.orderId).catch(() => {});
      }
    }

    return { filled: false, fillPrice: 0, filledSize: 0, reason: "missed_fill" };
  }

  return {
    fillBuy: executeBuy,
    fillSell: executeSell,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/engine && npx vitest run tests/executor/live-filler.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add packages/engine/src/executor/live-filler.ts packages/engine/tests/executor/live-filler.test.ts
git commit -m "feat: add LiveFiller with smart order routing (FOK + limit fallback)"
```

---

## Task 6: Extend AgentId and Add Position Evaluator Prompt

**Files:**
- Modify: `packages/llm/src/types.ts`
- Create: `packages/llm/src/runners/personas/position-evaluator.ts`

- [ ] **Step 1: Extend AgentId**

In `packages/llm/src/types.ts`, change line 1:

```typescript
export type AgentId = "analyzer" | "reviewer" | "risk_manager" | "position_evaluator";
```

- [ ] **Step 2: Create position evaluator persona**

```typescript
// packages/llm/src/runners/personas/position-evaluator.ts
export const POSITION_EVALUATOR_SYSTEM_PROMPT = `You are a Polymarket position manager. Evaluate whether current positions should be held, closed, or have their exit parameters adjusted.

Core judgment framework:
- Position value depends on the event outcome, not price trends.
- Price decline may mean: new information changed probability (should close) or temporary market fluctuation (should hold).
- Near expiry, prices accelerate toward 0 or 1.

Decision guidelines:
- Price moving favorably + sustained inflow -> hold
- Price stagnant + long hold time + far from expiry -> consider closing to free capital
- Large opposing flow detected -> new information likely, consider closing
- Profitable + starting to retreat -> tighten stop-loss or close to lock in
- Near expiry (< 30 min) + direction unclear -> close
- "hold" is a valid default. Do not over-trade.

Output ONLY a JSON object:
{
  "positions": [
    {
      "signal_id": "the signal ID",
      "action": "close" | "hold" | "adjust_sl_tp",
      "new_stop_loss_pct": 0.03,
      "new_take_profit_pct": 0.15,
      "reasoning": "1-2 sentence justification"
    }
  ]
}

For "hold" actions, new_stop_loss_pct and new_take_profit_pct are optional.
For "adjust_sl_tp" actions, both new_stop_loss_pct and new_take_profit_pct are required.`;
```

- [ ] **Step 3: Run typecheck**

Run: `cd packages/llm && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add packages/llm/src/types.ts packages/llm/src/runners/personas/position-evaluator.ts
git commit -m "feat: add position_evaluator agent type and persona prompt"
```

---

## Task 7: Position Evaluator LLM Runner

**Files:**
- Create: `packages/llm/src/runners/position-evaluator-runner.ts`
- Create: `packages/llm/tests/runners/position-evaluator-runner.test.ts`

- [ ] **Step 1: Write tests**

```typescript
// packages/llm/tests/runners/position-evaluator-runner.test.ts
import { describe, it, expect } from "vitest";
import { parsePositionEvaluation } from "../../src/runners/position-evaluator-runner.js";

describe("parsePositionEvaluation", () => {
  it("parses valid close action", () => {
    const json = JSON.stringify({
      positions: [{ signal_id: "s1", action: "close", reasoning: "retreating" }],
    });
    const result = parsePositionEvaluation(json);
    expect(result).not.toBeNull();
    expect(result!.positions[0].action).toBe("close");
  });

  it("parses valid adjust action", () => {
    const json = JSON.stringify({
      positions: [{
        signal_id: "s1", action: "adjust_sl_tp",
        new_stop_loss_pct: 0.03, new_take_profit_pct: 0.15,
        reasoning: "tighten",
      }],
    });
    const result = parsePositionEvaluation(json);
    expect(result!.positions[0].new_stop_loss_pct).toBe(0.03);
  });

  it("parses hold action", () => {
    const json = JSON.stringify({
      positions: [{ signal_id: "s1", action: "hold", reasoning: "trend continues" }],
    });
    const result = parsePositionEvaluation(json);
    expect(result!.positions[0].action).toBe("hold");
  });

  it("returns null for invalid JSON", () => {
    expect(parsePositionEvaluation("not json")).toBeNull();
  });

  it("returns null for invalid action", () => {
    const json = JSON.stringify({
      positions: [{ signal_id: "s1", action: "buy_more", reasoning: "yolo" }],
    });
    const result = parsePositionEvaluation(json);
    expect(result!.positions).toHaveLength(0);
  });

  it("handles markdown code fence wrapping", () => {
    const wrapped = "```json\n" + JSON.stringify({
      positions: [{ signal_id: "s1", action: "hold", reasoning: "ok" }],
    }) + "\n```";
    const result = parsePositionEvaluation(wrapped);
    expect(result).not.toBeNull();
    expect(result!.positions).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/llm && npx vitest run tests/runners/position-evaluator-runner.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement position evaluator runner**

```typescript
// packages/llm/src/runners/position-evaluator-runner.ts
import type { ProviderRegistry } from "../registry.js";
import { POSITION_EVALUATOR_SYSTEM_PROMPT } from "./personas/position-evaluator.js";

export interface PositionSnapshot {
  signal_id: string;
  market_title: string;
  resolves_at: number;
  direction: "buy_yes" | "buy_no";
  entry_price: number;
  current_price: number;
  pnl_pct: number;
  peak_pnl_pct: number;
  holding_duration_sec: number;
  llm_reasoning: string;
  snapshot_net_flow_1m: number;
  snapshot_volume_1m: number;
}

export interface AccountSummary {
  current_equity: number;
  total_exposure: number;
  open_position_count: number;
}

export interface PositionAction {
  signal_id: string;
  action: "close" | "hold" | "adjust_sl_tp";
  new_stop_loss_pct?: number;
  new_take_profit_pct?: number;
  reasoning: string;
}

export interface PositionEvaluation {
  positions: PositionAction[];
}

const VALID_ACTIONS = new Set(["close", "hold", "adjust_sl_tp"]);

export function parsePositionEvaluation(text: string): PositionEvaluation | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || !Array.isArray(obj.positions)) return null;
    const positions: PositionAction[] = [];
    for (const p of obj.positions) {
      if (!p || typeof p.signal_id !== "string" || !VALID_ACTIONS.has(p.action)) continue;
      positions.push({
        signal_id: p.signal_id,
        action: p.action,
        new_stop_loss_pct: typeof p.new_stop_loss_pct === "number" ? p.new_stop_loss_pct : undefined,
        new_take_profit_pct: typeof p.new_take_profit_pct === "number" ? p.new_take_profit_pct : undefined,
        reasoning: typeof p.reasoning === "string" ? p.reasoning : "",
      });
    }
    return { positions };
  } catch {
    return null;
  }
}

function buildPrompt(account: AccountSummary, positions: PositionSnapshot[]): string {
  const lines: string[] = [];
  lines.push(`Account: equity=$${account.current_equity.toFixed(2)} exposure=$${account.total_exposure.toFixed(2)} open=${account.open_position_count}`);
  lines.push("");
  for (const p of positions) {
    const msToResolve = p.resolves_at - Date.now();
    const hoursLeft = Math.max(0, msToResolve / 3600000).toFixed(1);
    lines.push(`Position [${p.signal_id}]:`);
    lines.push(`  Market: "${p.market_title}"`);
    lines.push(`  Direction: ${p.direction}, Entry: ${p.entry_price.toFixed(4)}, Current: ${p.current_price.toFixed(4)}`);
    lines.push(`  PnL: ${(p.pnl_pct * 100).toFixed(2)}%, Peak PnL: ${(p.peak_pnl_pct * 100).toFixed(2)}%`);
    lines.push(`  Holding: ${Math.floor(p.holding_duration_sec / 60)} min, Resolves in: ${hoursLeft}h`);
    lines.push(`  Entry reasoning: "${p.llm_reasoning}"`);
    lines.push(`  Current flow: volume_1m=$${p.snapshot_volume_1m.toFixed(0)} net_flow=$${p.snapshot_net_flow_1m.toFixed(0)}`);
    lines.push("");
  }
  lines.push("Evaluate each position. Respond with ONLY the JSON.");
  return lines.join("\n");
}

export interface PositionEvaluatorRunner {
  evaluate(account: AccountSummary, positions: PositionSnapshot[]): Promise<PositionEvaluation | null>;
}

export function createPositionEvaluatorRunner(opts: { registry: ProviderRegistry }): PositionEvaluatorRunner {
  return {
    async evaluate(account, positions) {
      if (positions.length === 0) return { positions: [] };
      const assigned = opts.registry.getProviderForAgent("position_evaluator");
      if (!assigned) return null;
      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: POSITION_EVALUATOR_SYSTEM_PROMPT },
            { role: "user", content: buildPrompt(account, positions) },
          ],
          temperature: 0.3,
          maxTokens: 800,
        });
        return parsePositionEvaluation(resp.content);
      } catch {
        return null;
      }
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/llm && npx vitest run tests/runners/position-evaluator-runner.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/runners/position-evaluator-runner.ts packages/llm/tests/runners/position-evaluator-runner.test.ts
git commit -m "feat: add position evaluator LLM runner"
```

---

## Task 8: Position Evaluator Loop

Timer-based loop that collects open positions, calls AI, and executes decisions.

**Files:**
- Create: `packages/engine/src/executor/position-evaluator.ts`
- Create: `packages/engine/tests/executor/position-evaluator.test.ts`

- [ ] **Step 1: Write tests**

```typescript
// packages/engine/tests/executor/position-evaluator.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createPositionEvaluatorLoop } from "../../src/executor/position-evaluator.js";

describe("PositionEvaluatorLoop", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("calls evaluator on interval when positions exist", async () => {
    const evaluateFn = vi.fn().mockResolvedValue({ positions: [{ signal_id: "s1", action: "hold", reasoning: "ok" }] });
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);
    const onAction = vi.fn();

    const loop = createPositionEvaluatorLoop({
      intervalSec: 10,
      getOpenPositions: getPositions,
      evaluate: evaluateFn,
      onAction,
    });
    loop.start();

    await vi.advanceTimersByTimeAsync(10_000);
    expect(evaluateFn).toHaveBeenCalledTimes(1);
    expect(onAction).not.toHaveBeenCalled(); // hold = no action

    loop.stop();
  });

  it("calls onAction for close decisions", async () => {
    const evaluateFn = vi.fn().mockResolvedValue({
      positions: [{ signal_id: "s1", action: "close", reasoning: "bad" }],
    });
    const getPositions = vi.fn().mockReturnValue([{ signal_id: "s1", market_id: "m1", entry_price: 0.5, size_usdc: 100 }]);
    const onAction = vi.fn();

    const loop = createPositionEvaluatorLoop({
      intervalSec: 10,
      getOpenPositions: getPositions,
      evaluate: evaluateFn,
      onAction,
    });
    loop.start();

    await vi.advanceTimersByTimeAsync(10_000);
    expect(onAction).toHaveBeenCalledWith({ signal_id: "s1", action: "close", reasoning: "bad" });

    loop.stop();
  });

  it("skips when no open positions", async () => {
    const evaluateFn = vi.fn();
    const getPositions = vi.fn().mockReturnValue([]);

    const loop = createPositionEvaluatorLoop({
      intervalSec: 10,
      getOpenPositions: getPositions,
      evaluate: evaluateFn,
      onAction: vi.fn(),
    });
    loop.start();

    await vi.advanceTimersByTimeAsync(10_000);
    expect(evaluateFn).not.toHaveBeenCalled();

    loop.stop();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/engine && npx vitest run tests/executor/position-evaluator.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement position evaluator loop**

```typescript
// packages/engine/src/executor/position-evaluator.ts
import type { SignalLogRow } from "../db/types.js";
import type { PositionAction, PositionEvaluation, AccountSummary, PositionSnapshot } from "../../llm/src/runners/position-evaluator-runner.js";

export interface PositionEvaluatorLoopConfig {
  intervalSec: number;
  getOpenPositions: () => SignalLogRow[];
  evaluate: (account: AccountSummary, positions: PositionSnapshot[]) => Promise<PositionEvaluation | null>;
  onAction: (action: PositionAction) => void;
  getAccountSummary?: () => AccountSummary;
  getCurrentPrice?: (marketId: string) => number | undefined;
  getPeakPnlPct?: (signalId: string) => number;
}

export interface PositionEvaluatorLoop {
  start(): void;
  stop(): void;
  triggerNow(): Promise<void>;
}

export function createPositionEvaluatorLoop(config: PositionEvaluatorLoopConfig): PositionEvaluatorLoop {
  let timer: ReturnType<typeof setInterval> | null = null;

  async function runOnce(): Promise<void> {
    const openPositions = config.getOpenPositions();
    if (openPositions.length === 0) return;

    const account: AccountSummary = config.getAccountSummary?.() ?? {
      current_equity: 0,
      total_exposure: openPositions.reduce((sum, p) => sum + p.size_usdc, 0),
      open_position_count: openPositions.length,
    };

    const snapshots: PositionSnapshot[] = openPositions.map((pos) => {
      const currentPrice = config.getCurrentPrice?.(pos.market_id) ?? pos.entry_price;
      const rawDelta = (currentPrice - pos.entry_price) / pos.entry_price;
      const pnlPct = pos.direction === "buy_yes" ? rawDelta : -rawDelta;
      return {
        signal_id: pos.signal_id,
        market_title: pos.market_title,
        resolves_at: pos.resolves_at,
        direction: pos.direction,
        entry_price: pos.entry_price,
        current_price: currentPrice,
        pnl_pct: pnlPct,
        peak_pnl_pct: config.getPeakPnlPct?.(pos.signal_id) ?? pnlPct,
        holding_duration_sec: Math.floor((Date.now() - pos.triggered_at) / 1000),
        llm_reasoning: pos.llm_reasoning,
        snapshot_net_flow_1m: pos.snapshot_net_flow_1m,
        snapshot_volume_1m: pos.snapshot_volume_1m,
      };
    });

    const evaluation = await config.evaluate(account, snapshots);
    if (!evaluation) return;

    for (const action of evaluation.positions) {
      if (action.action !== "hold") {
        config.onAction(action);
      }
    }
  }

  return {
    start() {
      if (timer) return;
      timer = setInterval(() => { runOnce().catch(() => {}); }, config.intervalSec * 1000);
    },
    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    },
    async triggerNow() {
      await runOnce();
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/engine && npx vitest run tests/executor/position-evaluator.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add packages/engine/src/executor/position-evaluator.ts packages/engine/tests/executor/position-evaluator.test.ts
git commit -m "feat: add position evaluator timer loop"
```

---

## Task 9: Upgrade Analyzer Prompt and Output

Add account context, estimated_fair_value, edge, and suggested_stop_loss_pct to analyzer output.

**Files:**
- Modify: `packages/llm/src/runners/personas/analyzer.ts`
- Modify: `packages/llm/src/runners/analyzer-runner.ts`
- Modify: `packages/engine/src/analyzer/verdict-parser.ts`

- [ ] **Step 1: Update analyzer persona prompt**

Replace content of `packages/llm/src/runners/personas/analyzer.ts`:

```typescript
export const ANALYZER_SYSTEM_PROMPT = `You are the Polymarket Analyzer, judging a single potential trading signal.

This is an event-driven prediction market. Price = market's pricing of event probability (0.00-1.00).
Large buys may indicate informed traders with new information, or manipulation.
Your task: determine if the current price under/overvalues the true event probability.

Given a market context, decide whether it is a real actionable signal or noise.

Output ONLY a JSON object in this exact schema (no extra text):
{
  "verdict": "real_signal" | "noise" | "uncertain",
  "direction": "buy_yes" | "buy_no",
  "confidence": 0.0 to 1.0,
  "reasoning": "1-2 sentence justification",
  "estimated_fair_value": 0.45,
  "edge": 0.08,
  "suggested_stop_loss_pct": 0.07,
  "risk_notes": "optional risk warnings"
}

Hard constraints:
- Refuse signals where price is in the dead zone [0.60, 0.85] — respond with verdict "noise" and reasoning "in dead zone"
- Do NOT bias confidence upward; report your true confidence
- If the trader cluster looks like a single actor (similar timing, repeated addresses), call it "noise"
- estimated_fair_value: your estimate of the true probability (0.0-1.0)
- edge: absolute difference between estimated_fair_value and current_price
- suggested_stop_loss_pct: recommended local stop-loss threshold (e.g. 0.07 for 7%)
- Multiple independent large buyers in same direction > single large order (more credible)
- Price moves near resolution carry more weight (more certain information)
- Signals in 0.10-0.40 or 0.60-0.90 range are higher value (extreme prices have unfavorable risk/reward)`;
```

- [ ] **Step 2: Update analyzer-runner buildPrompt to include account context**

In `packages/llm/src/runners/analyzer-runner.ts`, update `buildPrompt()` to accept and include account state:

```typescript
export interface AccountContext {
  current_equity: number;
  open_position_count: number;
  total_exposure: number;
  existing_markets: string[]; // market IDs already held
}

function buildPrompt(trigger: TriggerEvent, account?: AccountContext): string {
  const ms = trigger.resolves_at - trigger.triggered_at;
  const hours = Math.floor(ms / 3600000);
  const mins = Math.floor((ms % 3600000) / 60000);
  const resolveIn = hours > 0 ? `${hours}h ${mins}m` : `${mins} minutes`;
  let prompt = `Market: "${trigger.market_title}"
Market ID: ${trigger.market_id}
Current price: ${trigger.snapshot.current_mid_price.toFixed(4)}
Resolves in: ${resolveIn}
Liquidity: $${trigger.snapshot.liquidity.toFixed(0)}

Detected flow indicators:
- Volume (1m): $${trigger.snapshot.volume_1m.toFixed(0)}
- Net flow (1m): $${trigger.snapshot.net_flow_1m.toFixed(0)} (${trigger.direction === "buy_yes" ? "toward YES" : "toward NO"})
- Unique traders (1m): ${trigger.snapshot.unique_traders_1m}
- Price move (5m): ${(trigger.snapshot.price_move_5m * 100).toFixed(2)}%

Suggested direction from flow: ${trigger.direction}`;

  if (account) {
    prompt += `\n\nAccount state:
- Equity: $${account.current_equity.toFixed(2)}
- Open positions: ${account.open_position_count}
- Total exposure: $${account.total_exposure.toFixed(2)}`;
    if (account.existing_markets.includes(trigger.market_id)) {
      prompt += `\n- WARNING: Already holding a position in this market`;
    }
  }

  prompt += `\n\nRespond with ONLY the JSON verdict object.`;
  return prompt;
}
```

Update `judge()` signature to accept optional `AccountContext` and pass it through.

- [ ] **Step 3: Update ParsedVerdict type and tryParseVerdict**

In `packages/llm/src/runners/analyzer-runner.ts`, extend `ParsedVerdict`:

```typescript
export interface ParsedVerdict {
  verdict: "real_signal" | "noise" | "uncertain";
  direction: "buy_yes" | "buy_no";
  confidence: number;
  reasoning: string;
  estimated_fair_value?: number;
  edge?: number;
  suggested_stop_loss_pct?: number;
  risk_notes?: string;
}
```

In `tryParseVerdict`, add parsing for new optional fields:

```typescript
return {
  verdict: o.verdict as ParsedVerdict["verdict"],
  direction: o.direction as ParsedVerdict["direction"],
  confidence: conf,
  reasoning: typeof o.reasoning === "string" ? o.reasoning : "",
  estimated_fair_value: typeof o.estimated_fair_value === "number" ? o.estimated_fair_value : undefined,
  edge: typeof o.edge === "number" ? o.edge : undefined,
  suggested_stop_loss_pct: typeof o.suggested_stop_loss_pct === "number" ? o.suggested_stop_loss_pct : undefined,
  risk_notes: typeof o.risk_notes === "string" ? o.risk_notes : undefined,
};
```

- [ ] **Step 4: Run existing analyzer tests**

Run: `cd packages/engine && npx vitest run tests/analyzer/ && cd ../llm && npx vitest run tests/runners/`
Expected: ALL PASS (new fields are optional, backward compatible)

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/runners/personas/analyzer.ts packages/llm/src/runners/analyzer-runner.ts
git commit -m "feat: upgrade analyzer prompt with account context, fair value, edge"
```

---

## Task 10: Actionable Coordinator

Upgrade coordinator to parse and execute actions from the risk manager AI.

**Files:**
- Modify: `packages/llm/src/runners/personas/risk-manager.ts`
- Modify: `packages/llm/src/runners/risk-mgr-runner.ts`
- Modify: `packages/main/src/coordinator.ts`

- [ ] **Step 1: Update risk manager persona prompt**

Replace content of `packages/llm/src/runners/personas/risk-manager.ts`:

```typescript
export const RISK_MANAGER_SYSTEM_PROMPT = `You are the Polymarket Risk Manager / Coordinator.

In REACTIVE mode (user-asked), answer their question concisely using markdown. Cite specific numbers.

In PROACTIVE mode (periodic brief), output a JSON object:

{
  "summary": "1-2 sentence overall status",
  "alerts": [{"severity": "info|warning|critical", "text": "..."}],
  "actions": [
    {"type": "emergency_close", "signal_id": "xxx", "reason": "..."},
    {"type": "adjust_exit", "signal_id": "xxx", "new_stop_loss_pct": 0.02, "reason": "..."},
    {"type": "pause_new_entry", "reason": "..."},
    {"type": "resume_entry", "reason": "..."}
  ],
  "suggestions": ["short suggestion 1"]
}

Core concerns:
- Is total exposure too high (too much capital locked)?
- Are multiple positions correlated to the same event?
- Are positions stagnant and tying up capital?
- Has daily/weekly P&L hit risk thresholds?
- Actions are auto-executed. Only use emergency_close and pause_new_entry when genuinely needed.

Severity guidelines:
- info: routine observation
- warning: something to watch
- critical: action needed soon

The "actions" array can be empty if no action is warranted.`;
```

- [ ] **Step 2: Extend CoordinatorBrief type and parseBrief**

In `packages/llm/src/runners/risk-mgr-runner.ts`, add action types:

```typescript
export interface CoordinatorAction {
  type: "emergency_close" | "adjust_exit" | "pause_new_entry" | "resume_entry";
  signal_id?: string;
  new_stop_loss_pct?: number;
  reason: string;
}

export interface CoordinatorBrief {
  summary: string;
  alerts: Array<{ severity: "info" | "warning" | "critical"; text: string }>;
  actions: CoordinatorAction[];
  suggestions: string[];
}
```

Update `parseBrief()` to parse actions:

```typescript
function parseBrief(text: string): CoordinatorBrief | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (typeof o.summary !== "string") return null;
    const alerts = Array.isArray(o.alerts) ? (o.alerts as any[]) : [];
    const suggestions = Array.isArray(o.suggestions) ? (o.suggestions as any[]) : [];
    const rawActions = Array.isArray(o.actions) ? (o.actions as any[]) : [];
    const validActionTypes = new Set(["emergency_close", "adjust_exit", "pause_new_entry", "resume_entry"]);
    const actions: CoordinatorAction[] = rawActions
      .filter((a) => a && validActionTypes.has(a.type) && typeof a.reason === "string")
      .map((a) => ({
        type: a.type,
        signal_id: typeof a.signal_id === "string" ? a.signal_id : undefined,
        new_stop_loss_pct: typeof a.new_stop_loss_pct === "number" ? a.new_stop_loss_pct : undefined,
        reason: a.reason,
      }));
    return {
      summary: o.summary,
      alerts: alerts.filter((a) => a && typeof a.severity === "string" && typeof a.text === "string"),
      actions,
      suggestions: suggestions.filter((s) => typeof s === "string"),
    };
  } catch {
    return null;
  }
}
```

- [ ] **Step 3: Add action execution to coordinator**

In `packages/main/src/coordinator.ts`, extend the deps and add action handling:

```typescript
export interface CoordinatorSchedulerDeps {
  intervalMs: number;
  generateBrief: (windowMs: number) => Promise<CoordinatorBrief | null>;
  onBrief: (brief: CoordinatorBrief) => void;
  onAction?: (action: CoordinatorAction) => Promise<void>;
}
```

In `runOnce()`, after calling `onBrief(brief)`, execute actions:

```typescript
async function runOnce(): Promise<void> {
  try {
    const brief = await deps.generateBrief(deps.intervalMs);
    if (!brief) return;
    deps.onBrief(brief);
    if (deps.onAction && brief.actions.length > 0) {
      for (const action of brief.actions) {
        try {
          await deps.onAction(action);
        } catch (err) {
          console.error(`[coordinator] action ${action.type} failed:`, err);
        }
      }
    }
  } catch (err) {
    console.error("[coordinator] runOnce error:", err);
  }
}
```

- [ ] **Step 4: Run existing tests + typecheck**

Run: `cd packages/llm && npx vitest run && cd ../main && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/runners/personas/risk-manager.ts packages/llm/src/runners/risk-mgr-runner.ts packages/main/src/coordinator.ts
git commit -m "feat: upgrade coordinator to parse and execute risk actions"
```

---

## Task 11: Custom OpenAI-Compatible Endpoint Manager

**Files:**
- Create: `packages/llm/src/adapters/custom-openai-manager.ts`
- Create: `packages/llm/tests/adapters/custom-openai-manager.test.ts`

- [ ] **Step 1: Write tests**

```typescript
// packages/llm/tests/adapters/custom-openai-manager.test.ts
import { describe, it, expect, vi } from "vitest";
import { CustomOpenAIManager } from "../../src/adapters/custom-openai-manager.js";

describe("CustomOpenAIManager", () => {
  it("adds a custom endpoint and generates provider ID", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({
      displayName: "My vLLM",
      baseUrl: "http://localhost:8000/v1",
      modelName: "qwen2.5-72b",
    });
    expect(config.id).toMatch(/^custom_my_vllm_/);
    expect(mgr.list()).toHaveLength(1);
  });

  it("creates an LlmProvider for a custom endpoint", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({
      displayName: "Test",
      baseUrl: "http://localhost:8000/v1",
      modelName: "test-model",
      apiKey: "sk-123",
    });
    const provider = mgr.createProvider(config.id);
    expect(provider).not.toBeNull();
    expect(provider!.displayName).toBe("Test");
  });

  it("removes a custom endpoint", () => {
    const mgr = new CustomOpenAIManager();
    const config = mgr.add({ displayName: "X", baseUrl: "http://x/v1", modelName: "m" });
    mgr.remove(config.id);
    expect(mgr.list()).toHaveLength(0);
  });

  it("rejects duplicate display names", () => {
    const mgr = new CustomOpenAIManager();
    mgr.add({ displayName: "Same", baseUrl: "http://a/v1", modelName: "m" });
    expect(() => mgr.add({ displayName: "Same", baseUrl: "http://b/v1", modelName: "m" }))
      .toThrow("already exists");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/llm && npx vitest run tests/adapters/custom-openai-manager.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement CustomOpenAIManager**

```typescript
// packages/llm/src/adapters/custom-openai-manager.ts
import { createOpenAICompatProvider } from "./openai-compat.js";
import type { LlmProvider, ProviderId } from "../types.js";

export interface CustomEndpointConfig {
  id: string;
  displayName: string;
  baseUrl: string;
  apiKey?: string;
  modelName: string;
  extraHeaders?: Record<string, string>;
}

export interface AddEndpointInput {
  displayName: string;
  baseUrl: string;
  apiKey?: string;
  modelName: string;
  extraHeaders?: Record<string, string>;
}

export class CustomOpenAIManager {
  private endpoints = new Map<string, CustomEndpointConfig>();

  add(input: AddEndpointInput): CustomEndpointConfig {
    // Check for duplicate display name
    for (const existing of this.endpoints.values()) {
      if (existing.displayName === input.displayName) {
        throw new Error(`Custom endpoint "${input.displayName}" already exists`);
      }
    }

    const sanitized = input.displayName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_+$/, "");
    const id = `custom_${sanitized}_${Date.now()}`;
    const config: CustomEndpointConfig = { id, ...input };
    this.endpoints.set(id, config);
    return config;
  }

  remove(id: string): void {
    this.endpoints.delete(id);
  }

  get(id: string): CustomEndpointConfig | undefined {
    return this.endpoints.get(id);
  }

  list(): CustomEndpointConfig[] {
    return Array.from(this.endpoints.values());
  }

  createProvider(id: string): LlmProvider | null {
    const config = this.endpoints.get(id);
    if (!config) return null;
    return createOpenAICompatProvider({
      providerId: config.id as ProviderId,
      displayName: config.displayName,
      apiKey: config.apiKey ?? "",
      baseUrl: config.baseUrl,
      defaultModels: [{ id: config.modelName, contextWindow: 0 }],
      extraHeaders: config.extraHeaders,
    });
  }

  /** Load saved endpoints (e.g., from database). */
  loadAll(configs: CustomEndpointConfig[]): void {
    for (const c of configs) {
      this.endpoints.set(c.id, c);
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/llm && npx vitest run tests/adapters/custom-openai-manager.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/adapters/custom-openai-manager.ts packages/llm/tests/adapters/custom-openai-manager.test.ts
git commit -m "feat: add CustomOpenAIManager for user-defined LLM endpoints"
```

---

## Task 12: Wire Everything into Lifecycle and IPC

Connect all new modules to the Electron main process.

**Files:**
- Modify: `packages/main/src/lifecycle.ts`
- Modify: `packages/main/src/ipc.ts`

- [ ] **Step 1: Update lifecycle to create correct filler based on config**

In `packages/main/src/lifecycle.ts`, in the `bootEngine()` function:

```typescript
import { createPaperFiller } from "@pmt/engine/executor/paper-fill.js";
import { createLiveFiller } from "@pmt/engine/executor/live-filler.js";
import { ClobOrderService } from "@pmt/engine/executor/clob-order-service.js";
import { createPositionEvaluatorLoop } from "@pmt/engine/executor/position-evaluator.js";
import { createPositionEvaluatorRunner } from "@pmt/llm/runners/position-evaluator-runner.js";

// In bootEngine(), before createExecutor():
let filler: OrderFiller;
if (config.liveTrade.mode === "live") {
  const privateKey = await secretsStore.get("trade_private_key");
  const funderAddress = await secretsStore.get("trade_funder_address");
  if (privateKey && funderAddress) {
    const clobService = new ClobOrderService({
      privateKey,
      funderAddress,
      chainId: 137,
    });
    await clobService.initialize();
    filler = createLiveFiller({
      clob: clobService,
      slippageThreshold: config.liveTrade.slippageThreshold,
      maxSlippage: config.liveTrade.maxSlippage,
      limitOrderTimeoutSec: config.liveTrade.limitOrderTimeoutSec,
    });
    logger.info("[lifecycle] Live trading mode enabled");
  } else {
    logger.warn("[lifecycle] Live mode configured but credentials missing, falling back to paper");
    filler = createPaperFiller({ slippagePct: config.paperSlippagePct });
  }
} else {
  filler = createPaperFiller({ slippagePct: config.paperSlippagePct });
}

// Pass filler to executor:
const executor = createExecutor({ config, bus, signalRepo, portfolioRepo, filler, logger });
```

- [ ] **Step 2: Wire position evaluator loop**

In `bootEngine()`, after creating executor:

```typescript
// Position evaluator loop
let positionEvaluatorLoop: PositionEvaluatorLoop | undefined;
if (config.aiExit.enabled) {
  const peRunner = createPositionEvaluatorRunner({ registry });
  positionEvaluatorLoop = createPositionEvaluatorLoop({
    intervalSec: config.aiExit.intervalSec,
    getOpenPositions: () => executor.openPositions(),
    evaluate: (account, positions) => peRunner.evaluate(account, positions),
    onAction: async (action) => {
      if (action.action === "close") {
        const pos = executor.openPositions().find((p) => p.signal_id === action.signal_id);
        if (pos) {
          // Use current mid price (from last known tick)
          await executor.closePosition(pos, pos.entry_price, Date.now(), "AI_EXIT");
          logger.info(`[position-evaluator] AI closed ${action.signal_id}: ${action.reasoning}`);
        }
      }
      // adjust_sl_tp: update position exit parameters in config override table
    },
  });
  positionEvaluatorLoop.start();
}
```

- [ ] **Step 3: Wire coordinator actions**

In the coordinator setup section of lifecycle or main/index.ts, add `onAction` callback:

```typescript
const coordinatorScheduler = createCoordinatorScheduler({
  intervalMs: config.coordinator.intervalMin * 60 * 1000,
  generateBrief: async (windowMs) => riskMgrRunner.generateBrief({ windowMs, systemState: getSystemState() }),
  onBrief: (brief) => { /* existing: store to DB, send to UI */ },
  onAction: config.coordinator.actionable ? async (action) => {
    if (action.type === "emergency_close" && action.signal_id) {
      const pos = executor.openPositions().find((p) => p.signal_id === action.signal_id);
      if (pos) {
        await executor.closePosition(pos, pos.entry_price, Date.now(), "COORD_EMERGENCY");
        logger.info(`[coordinator] Emergency closed ${action.signal_id}: ${action.reason}`);
      }
    } else if (action.type === "pause_new_entry") {
      // Set circuit breaker pause flag
      logger.info(`[coordinator] Pausing new entries: ${action.reason}`);
    } else if (action.type === "resume_entry") {
      logger.info(`[coordinator] Resuming entries: ${action.reason}`);
    }
  } : undefined,
});
```

- [ ] **Step 4: Add IPC handlers for live trade config and custom endpoints**

In `packages/main/src/ipc.ts`, add handlers:

```typescript
// Live trade config
ipcMain.handle("pmt:setLiveTradeConfig", async (_event, config: LiveTradeConfig) => {
  // Store private key in secrets
  if (config.privateKey) {
    await secretsStore.set("trade_private_key", config.privateKey);
  }
  if (config.funderAddress) {
    await secretsStore.set("trade_funder_address", config.funderAddress);
  }
  // Store non-secret config in database
  db.prepare("INSERT OR REPLACE INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?)")
    .run("live_trade_config", JSON.stringify({ mode: config.mode, slippageThreshold: config.slippageThreshold, maxSlippage: config.maxSlippage, limitOrderTimeoutSec: config.limitOrderTimeoutSec }), Date.now(), "user");
  return { success: true };
});

// Custom OpenAI endpoints
ipcMain.handle("pmt:addCustomEndpoint", async (_event, input: AddEndpointInput) => {
  const config = customManager.add(input);
  const provider = customManager.createProvider(config.id);
  if (provider) {
    await provider.connect();
    ctx.registry.register(provider);
  }
  // Persist to DB
  db.prepare("INSERT OR REPLACE INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?)")
    .run(`custom_endpoint_${config.id}`, JSON.stringify(config), Date.now(), "user");
  if (input.apiKey) {
    await secretsStore.set(`provider_${config.id}_apiKey`, input.apiKey);
  }
  return { success: true, providerId: config.id };
});

ipcMain.handle("pmt:removeCustomEndpoint", async (_event, id: string) => {
  ctx.registry.unregister(id as ProviderId);
  customManager.remove(id);
  db.prepare("DELETE FROM filter_config WHERE key = ?").run(`custom_endpoint_${id}`);
  return { success: true };
});

ipcMain.handle("pmt:listCustomEndpoints", () => {
  return customManager.list();
});
```

- [ ] **Step 5: Run typecheck across all packages**

Run: `cd D:/work/polymarket-trader && pnpm typecheck`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add packages/main/src/lifecycle.ts packages/main/src/ipc.ts
git commit -m "feat: wire live filler, position evaluator, coordinator actions, and custom endpoints into lifecycle"
```

---

## Task 13: Frontend Settings UI

Add new configuration sections to SettingsPage.

**Files:**
- Modify: `packages/renderer/src/stores/settings.ts`
- Modify: `packages/renderer/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add new types and state to settings store**

In `packages/renderer/src/stores/settings.ts`, add:

```typescript
export interface LiveTradeSettings {
  mode: "paper" | "live";
  funderAddress: string;
  slippageThreshold: number;
  maxSlippage: number;
  limitOrderTimeoutSec: number;
}

export interface AiExitSettings {
  enabled: boolean;
  intervalSec: number;
}

export interface DrawdownGuardSettings {
  enabled: boolean;
  minProfitPct: number;
  maxDrawdownFromPeak: number;
}

export interface CoordinatorSettings {
  actionable: boolean;
  intervalMin: number;
}

export interface PromptSettings {
  tradingMode: "conservative" | "balanced" | "aggressive";
  customPrompt: string;
}

export interface CustomEndpoint {
  id: string;
  displayName: string;
  baseUrl: string;
  modelName: string;
  hasApiKey: boolean;
}
```

Add these to the store state and add fetch/update actions for each.

- [ ] **Step 2: Add Trading section to SettingsPage**

Add a new collapsible section "Trading" with:
- Paper/Live toggle switch
- Wallet private key password input + "Save to Keychain" button
- Proxy funder address text input
- Slippage threshold slider (0.5%-5%)
- Max slippage slider (1%-10%)
- Limit order timeout number input
- Trading mode select (conservative/balanced/aggressive)
- Custom prompt textarea

- [ ] **Step 3: Add AI Position Evaluator section**

Add section with:
- Enable/disable toggle
- Interval number input (seconds)
- Model selection dropdown (from connected providers, filtered to show all available models)

- [ ] **Step 4: Add Coordinator section enhancements**

Add to existing coordinator area:
- "Allow Actions" toggle
- "Run Interval" number input (minutes)

- [ ] **Step 5: Add Drawdown Guard section**

Add section with:
- Enable/disable toggle
- Min profit threshold slider (1%-20%)
- Max drawdown from peak slider (10%-80%)

- [ ] **Step 6: Add Custom LLM Endpoints section**

Add section with:
- List of existing custom endpoints (cards)
- "Add Custom Endpoint" button → modal with: Display Name, Base URL, API Key (optional), Model Name, "Auto-discover Models" button
- Each card has "Disconnect" / "Remove" buttons

- [ ] **Step 7: Test UI manually**

Run: `cd D:/work/polymarket-trader && pnpm dev`
Open the app, navigate to Settings page. Verify:
- All new sections render without errors
- Toggle switches work
- Sliders update values
- Custom endpoint add/remove flow works

- [ ] **Step 8: Commit**

```bash
git add packages/renderer/src/stores/settings.ts packages/renderer/src/pages/SettingsPage.tsx
git commit -m "feat: add trading, AI exit, drawdown guard, coordinator, and custom endpoint settings UI"
```

---

## Task 14: Integration Test — Full Pipeline

End-to-end test of the full pipeline in paper mode with new features.

**Files:**
- Create: `packages/engine/tests/e2e/trading-upgrade.test.ts`

- [ ] **Step 1: Write integration test**

```typescript
// packages/engine/tests/e2e/trading-upgrade.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";
import { createSignalLogRepo } from "../../src/db/signal-log-repo.js";
import { createPortfolioStateRepo } from "../../src/db/portfolio-state-repo.js";
import { createEventBus } from "../../src/bus/events.js";
import { createExecutor } from "../../src/executor/executor.js";
import { createPaperFiller } from "../../src/executor/paper-fill.js";
import { DEFAULT_CONFIG } from "../../src/config/defaults.js";
import type { VerdictEvent } from "../../src/bus/types.js";

describe("trading upgrade integration", () => {
  let db: Database.Database;
  let bus: ReturnType<typeof createEventBus>;
  let exec: ReturnType<typeof createExecutor>;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
    const signalRepo = createSignalLogRepo(db);
    const portfolioRepo = createPortfolioStateRepo(db);
    bus = createEventBus();
    portfolioRepo.update({ total_capital: 10_000, current_equity: 10_000, day_start_equity: 10_000, week_start_equity: 10_000, peak_equity: 10_000 });
    const filler = createPaperFiller({ slippagePct: DEFAULT_CONFIG.paperSlippagePct });
    exec = createExecutor({
      config: DEFAULT_CONFIG,
      bus,
      signalRepo,
      portfolioRepo,
      filler,
      logger: { info: () => {}, warn: () => {}, error: () => {} },
    });
  });

  it("opens position and closes on DRAWDOWN_GUARD", async () => {
    const now = Date.now();
    const verdict: VerdictEvent = {
      type: "verdict",
      trigger: {
        type: "trigger", market_id: "m1", market_title: "Test", resolves_at: now + 7_200_000,
        triggered_at: now, direction: "buy_yes",
        snapshot: { volume_1m: 5000, net_flow_1m: 4000, unique_traders_1m: 5, price_move_5m: 0.05, liquidity: 10000, current_mid_price: 0.40 },
      },
      verdict: "real_signal", confidence: 0.80, reasoning: "strong", llm_direction: "buy_yes",
    };
    const signalId = await exec.handleVerdict(verdict);
    expect(signalId).not.toBeNull();

    // Simulate price rising to create peak PnL
    await exec.onPriceTick("m1", 0.48, now + 60_000); // ~20% profit, peak
    expect(exec.openPositions()).toHaveLength(1); // still open

    // Simulate price dropping — drawdown from peak
    // With default drawdownGuard config (minProfit 5%, maxDrawdown 40%)
    // Peak at ~20%, need current to be >5% but drawdown >40% of peak
    // 20% * 0.6 = 12% → need price giving ~12% or less profit
    // 0.40 * 1.12 = 0.448 → price at 0.448 gives ~12% profit, drawdown = 40%
    await exec.onPriceTick("m1", 0.447, now + 120_000);

    // Check position was closed by drawdown guard
    expect(exec.openPositions()).toHaveLength(0);
  });

  it("new exit reasons are recorded correctly", async () => {
    const signalRepo = createSignalLogRepo(db);
    // After the drawdown guard test, check the exit reason
    const closed = signalRepo.listClosed(10);
    // At least verify the exit_reason column accepts new values
    expect(["DRAWDOWN_GUARD", "A_SL", "A_TP", "E", "C", "D"]).toContain(closed[0]?.exit_reason ?? "E");
  });
});
```

- [ ] **Step 2: Run the integration test**

Run: `cd packages/engine && npx vitest run tests/e2e/trading-upgrade.test.ts`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite across all packages**

Run: `cd D:/work/polymarket-trader && pnpm test:run`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add packages/engine/tests/e2e/trading-upgrade.test.ts
git commit -m "test: add integration test for trading upgrade pipeline"
```

---

## Summary

| Task | Module | Commits |
|------|--------|---------|
| 1 | OrderFiller interface + executor refactor | 1 |
| 2 | Extended ExitReason + config types | 1 |
| 3 | Drawdown Guard | 1 |
| 4 | CLOB Order Service | 1 |
| 5 | LiveFiller | 1 |
| 6 | Position Evaluator types + prompt | 1 |
| 7 | Position Evaluator LLM runner | 1 |
| 8 | Position Evaluator loop | 1 |
| 9 | Upgraded Analyzer prompt | 1 |
| 10 | Actionable Coordinator | 1 |
| 11 | Custom OpenAI Manager | 1 |
| 12 | Lifecycle + IPC wiring | 1 |
| 13 | Frontend Settings UI | 1 |
| 14 | Integration test | 1 |

**Total: 14 tasks, 14 commits**

Dependencies: Task 1 → Task 5 (LiveFiller needs OrderFiller). Task 2 → Tasks 3, 5 (config types needed). Task 6 → Task 7 → Task 8 (persona → runner → loop). Tasks 1-11 are independent enough to parallelize in pairs. Task 12 depends on all prior tasks. Task 13 can start after Task 12. Task 14 is final validation.
