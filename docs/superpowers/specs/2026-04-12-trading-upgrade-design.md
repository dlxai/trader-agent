# Polymarket Trader - Trading Upgrade Design

> Date: 2026-04-12
> Approach: Incremental Integration (Plan A)
> Reference: NoFxAiOS/nofx for AI config patterns, adapted to Polymarket specifics

## Overview

Upgrade polymarket-trader from a paper-trading signal analyzer to a full live-trading system with AI-driven position management, multi-layer risk controls, and flexible LLM provider configuration.

### Scope

1. **Real Order Execution** - Replace paper-fill with Polymarket CLOB API integration
2. **AI-Driven Position Exit** - AI periodically re-evaluates all open positions
3. **Actionable Coordinator** - Upgrade from passive briefs to executable risk actions
4. **Independent Drawdown Guard** - Automatic profit drawdown protection
5. **Custom OpenAI-Compatible Endpoints** - User-configurable LLM endpoints
6. **Prompt & Decision Redesign** - Polymarket-specific AI decision framework
7. **Frontend Configuration UI** - All new settings exposed in Settings page

### Key Constraints

- Polymarket is a **binary prediction market**, not a futures exchange
- **No exchange-level SL/TP orders** - all exit logic is client-side
- **Proxy wallet mode** (signature_type=2) - signer and funder addresses differ
- Paper-fill mode retained as dry-run fallback via config toggle

---

## 1. Real Order Execution

### Architecture

```
executor.ts: handleVerdict()
    |
    v
OrderFiller interface
    |-- PaperFiller (existing, retained for dry-run)
    +-- LiveFiller (new)
            |
            v
        ClobOrderService (new)
            |-- Init: wallet private key -> derive API credentials
            |-- Order: createAndPostOrder()
            |-- Query: getBalanceAllowance(), getOrders()
            +-- Cancel: cancel(), cancelAll()
```

### OrderFiller Interface

```typescript
interface OrderFiller {
  fillBuy(params: FillParams): Promise<FillResult>;
  fillSell(params: FillParams): Promise<FillResult>;
}

interface FillParams {
  tokenId: string;
  sizeUsdc: number;
  direction: "buy_yes" | "buy_no";
  market: MarketMetadata;
}

interface FillResult {
  filled: boolean;
  fillPrice: number;
  filledSize: number;
  orderId?: string;
  reason?: "filled" | "partial" | "missed_fill" | "insufficient_balance";
}
```

### LiveFiller Execution Flow

```
1. Receive verdict (real_signal, direction, confidence)
2. Fetch order book -> calculate mid price & spread
3. Slippage check:
   - Deviation <= slippageThreshold (default 2%) -> market order (FOK)
   - Deviation > slippageThreshold -> limit order (GTC) at mid +/- maxSlippage
4. Submit order -> await confirmation
5. FOK not filled -> downgrade to limit order, set timeout (default 60s)
6. Limit order timeout -> cancel order, record "missed_fill"
7. On fill -> write to signal_log, update position tracker
```

### Close Position Flow

```
1. evaluateExit() triggers close
2. Submit FOK sell order at best bid price
3. FOK fails (low liquidity) -> downgrade to FAK (partial fill allowed)
4. Remaining unfilled -> retry up to 3 times:
   - Retry 1: best bid - 1 tick
   - Retry 2: best bid - 2 ticks
   - Retry 3: best bid - 5 ticks (aggressive, accept worse price to ensure exit)
5. After 3 retries still unfilled -> log "close_failed" alert, notify UI
6. Record exit in signal_log with actual fill price (volume-weighted if partial fills)
```

### Authentication (Proxy Wallet)

- **signature_type = 2** (browser proxy mode)
- User provides: wallet private key + proxy funder address
- API credentials derived on first use via `createOrDeriveApiKey()`
- All secrets stored in OS keychain (existing secrets store)
- Token allowances checked on first connection; prompt user if insufficient

### Configuration

```typescript
interface LiveTradeConfig {
  mode: "paper" | "live";              // Global toggle, default "paper"
  privateKey: string;                  // Stored in OS keychain
  funderAddress: string;               // Polymarket proxy contract address
  signatureType: 2;                    // Browser proxy
  slippageThreshold: number;           // Default 0.02 (2%)
  maxSlippage: number;                 // Default 0.03 (3%)
  limitOrderTimeout: number;           // Default 60 seconds
}
```

### Safety Measures

- Private key encrypted in OS keychain, never on disk
- USDC balance checked before every order
- Token allowance verified on connection
- Paper mode retained as one-toggle fallback

---

## 2. AI-Driven Position Exit

### Architecture

New periodic AI evaluation loop, independent of existing rule-based exit checks.

```
Timer (default 180s)
    |
    v
AI Position Evaluator (new agent role: "position_evaluator")
    |
    v
Collect all open positions + current market snapshots
    |
    v
Build prompt with position details
    |
    v
Call LLM -> parse per-position decisions
    |
    v
For each position:
  close        -> executor.closePosition(reason: "AI_EXIT")
  adjust_sl_tp -> update local SL/TP monitoring thresholds
  hold         -> no action
```

### Relationship to Existing Exit System

```
Defense Layer 1: Rule-based exit (every price tick)    - SL/TP/timeout/expiry/reverse signal
Defense Layer 2: AI Position Evaluator (every 3 min)   - Holistic per-position analysis
Defense Layer 3: Coordinator emergency (every 30 min)  - Portfolio-level risk actions
Defense Layer 4: Drawdown Guard (every price tick)     - Profit drawdown auto-close
```

Rule-based exit takes priority. If a rule already closed a position, AI will not re-evaluate it.

### AI Output Format

```json
{
  "positions": [
    {
      "signal_id": "xxx",
      "action": "close",
      "reasoning": "Profit retreated 35% from peak, opposing flow detected"
    },
    {
      "signal_id": "yyy",
      "action": "hold",
      "reasoning": "Trend continuing, net inflow increasing"
    },
    {
      "signal_id": "zzz",
      "action": "adjust_sl_tp",
      "new_stop_loss_pct": 0.03,
      "new_take_profit_pct": 0.15,
      "reasoning": "Tighten stop-loss to lock in profit"
    }
  ]
}
```

### Failure Tolerance

- AI call failure does not affect rule-based exits
- After 3 consecutive failures, log warning but do not enter safe mode (rules still protect)
- Resume evaluation on next successful call

### Configuration

```typescript
interface AiExitConfig {
  enabled: boolean;             // Default true
  intervalSec: number;          // Default 180 (3 minutes)
  agentId: "position_evaluator"; // Independently configurable model
}
```

---

## 3. Actionable Coordinator

### Current State

Coordinator runs hourly, generates text brief with summary + alerts + suggestions. No executable actions.

### Upgrade

Add `actions` array to Coordinator output. System auto-executes approved action types.

### Output Format

```json
{
  "summary": "Portfolio up 3.2%, but market-A showing significant drawdown",
  "alerts": [
    { "severity": "critical", "text": "market-A profit retreated from 8% to 2%" }
  ],
  "actions": [
    {
      "type": "emergency_close",
      "signal_id": "xxx",
      "reason": "Profit drawdown exceeds 70%, flow reversal detected"
    },
    {
      "type": "adjust_exit",
      "signal_id": "yyy",
      "new_stop_loss_pct": 0.02,
      "reason": "Tighten stop-loss to protect gains"
    },
    {
      "type": "pause_new_entry",
      "reason": "Daily loss approaching threshold"
    }
  ],
  "suggestions": ["Consider reducing overall exposure"]
}
```

### Action Types

| Action | Effect | Implementation |
|--------|--------|----------------|
| `emergency_close` | Close a specific position immediately | `executor.closePosition(reason: "COORD_EMERGENCY")` |
| `adjust_exit` | Update local SL/TP monitoring thresholds | Update position's exit parameters |
| `pause_new_entry` | Halt new position opening | Set circuit breaker flag |
| `resume_entry` | Resume new position opening | Clear circuit breaker flag |

### Relationship to AI Position Evaluator

| Dimension | AI Position Evaluator | Coordinator |
|-----------|----------------------|-------------|
| Frequency | Every 3 minutes | User-configurable (default 30 min) |
| Scope | Per-position detailed analysis | Portfolio-level risk overview |
| Trigger | Routine evaluation | Abnormal/emergency situations |
| Analogy | Trader managing each position | Risk manager watching the desk |

### Configuration

```typescript
interface CoordinatorConfig {
  actionable: boolean;          // Allow executing actions, default true
  intervalMin: number;          // Run interval in minutes, user-configurable, default 30
}
```

---

## 4. Independent Drawdown Guard

### Purpose

Last line of defense. Pure rule-based, zero-latency, no AI dependency. Runs on every price tick alongside existing exit checks.

### Logic

```
On each price tick for each open position:
  1. Calculate current pnl%
  2. Update peakPnl% (historical max profit percentage)
  3. Calculate drawdown = (peakPnl - currentPnl) / peakPnl
  4. Trigger condition: currentPnl > minProfitPct AND drawdown >= maxDrawdownFromPeak
     -> Auto close, reason: "DRAWDOWN_GUARD"
```

### Example

Position peaked at +10% profit, now at +5.5%.
Drawdown = (10 - 5.5) / 10 = 45% > 40% threshold -> trigger close, locking in 5.5% profit.

### Integration

Added as a new check in existing `evaluateExit()` function, with exit reason `"DRAWDOWN_GUARD"`. Runs after SL/TP checks, before AI evaluation. Reuses existing price tick event - no independent timer needed.

### State

- `peakPnlMap: Map<string, number>` in memory, keyed by signal_id
- Initialized from current pnl% on position open
- Updated on every price tick
- Cleared on position close

### Configuration

```typescript
interface DrawdownGuardConfig {
  enabled: boolean;                // Default true
  minProfitPct: number;            // Minimum profit threshold, default 0.05 (5%)
  maxDrawdownFromPeak: number;     // Maximum drawdown ratio, default 0.40 (40%)
}
```

---

## 5. Custom OpenAI-Compatible Endpoints

### Current Problem

Adding a new LLM provider requires code changes in 3 files:
- `ipc.ts` - connectProvider switch statement
- `lifecycle.ts` - loadStoredProviders switch statement
- `types.ts` - ProviderId union type

### Solution

Add a generic `custom_openai` provider type. Users configure endpoints via UI without code changes.

### Architecture

```
Existing providers (unchanged):
  anthropic, openai, deepseek, zhipu ... -> hardcoded endpoints

New:
  custom_openai -> user-configured endpoints
    |-- Custom 1: "Local vLLM" -> http://localhost:8000/v1
    |-- Custom 2: "Internal API" -> https://llm.internal.com/v1
    +-- Custom 3: "Other" -> https://xxx.com/v1
```

### User Flow

```
Settings -> LLM Providers -> "Add Custom Endpoint" button
  |
  v
Modal:
  - Display Name: "My vLLM"
  - Base URL: http://localhost:8000/v1
  - API Key: sk-xxx (optional, some local deployments don't need it)
  - Model Name: qwen2.5-72b (manual input, or click "Auto-discover" to call /models)
  |
  v
Click Connect -> validate endpoint reachable -> register as provider
  |
  v
Available in agent assignment: analyzer -> "My vLLM / qwen2.5-72b"
```

### Data Storage

- `providerId` auto-generated: `custom_${sanitized_name}_${timestamp}`
- API key stored in OS keychain
- baseUrl + displayName + modelName stored in database `filter_config` table
- Multiple custom endpoints supported simultaneously

### Configuration

```typescript
interface CustomOpenAIConfig {
  id: string;                               // Auto-generated
  displayName: string;                      // User-chosen name
  baseUrl: string;                          // OpenAI-compatible endpoint
  apiKey?: string;                          // Optional
  modelName: string;                        // Model identifier
  extraHeaders?: Record<string, string>;    // Optional extra headers
}
```

---

## 6. Prompt & Decision Design (Polymarket-Specific)

### Design Principle

Polymarket is a binary prediction market, not a futures exchange. The AI must reason about **event probability** vs **market pricing**, not price trends and technical indicators.

Key differences from crypto futures (nofx):
- Price range is 0.00-1.00 (probability), outcome is binary (win $1 or lose all)
- No leverage, no margin, no liquidation, no funding rates
- "Short" = buying NO tokens (equivalent to shorting YES)
- Hold times can be hours to weeks (waiting for event resolution)
- Core signal is probability mispricing, not momentum

### 6.1 Analyzer Prompt (Upgraded)

**Current:** Only judges signal as real_signal / noise / uncertain.
**Upgraded:** Judges signal + provides entry guidance.

```
Role: You are a Polymarket prediction market analyst. Your job is to determine
whether a market signal reflects a genuine probability shift or short-term noise.

Core judgment framework:
  - This is an event-driven market. Price = market's pricing of event probability.
  - Large buys may indicate: informed traders with new information, or manipulation.
  - Your task: Is the current price under/overvaluing the true event probability?

Input:
  - Market title (event description)
  - Resolution time (time until settlement)
  - Current YES token price
  - Trigger snapshot: 1m/5m volume, net flow, unique traders, price movement
  - Current account state (balance, position count, total exposure)  [NEW]
  - Existing positions summary (avoid conflicts)  [NEW]

Judgment guidelines:
  - Multiple independent large buyers in same direction > single large order (more credible)
  - Price moves near resolution carry more weight (more certain information)
  - Signals in 0.10-0.40 or 0.60-0.90 range are higher value
    (extreme prices <0.10 or >0.90 have high risk, low reward)
  - Signals in dead zone [0.60-0.85] require stronger evidence

Output:
{
  "verdict": "real_signal" | "noise" | "uncertain",
  "direction": "buy_yes" | "buy_no",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "estimated_fair_value": 0.45,       // AI's estimated fair probability  [NEW]
  "edge": 0.08,                       // Estimated edge = |fair_value - current_price|  [NEW]
  "suggested_stop_loss_pct": 0.07,    // Local monitoring threshold  [NEW]
  "risk_notes": "..."                 // Risk warnings  [NEW]
}
```

Note: No leverage or position size suggestions. Kelly criterion already calculates sizing based on binary payoff structure. AI focuses on **probability judgment**.

### 6.2 Position Evaluator Prompt (New)

```
Role: You are a Polymarket position manager. Evaluate whether current positions
should be held, closed, or have their exit parameters adjusted.

Core judgment framework:
  - Position value depends on the event outcome, not price trends.
  - Price decline may mean: new information changed probability (should close)
    or temporary market fluctuation (should hold).
  - Near expiry, prices accelerate toward 0 or 1.

Input (per position):
  - Market title, resolution time
  - Direction (YES/NO), entry price, current price
  - PnL%, peak PnL%, holding duration
  - Entry-time AI reasoning and estimated_fair_value
  - Current market snapshot (1m/5m volume, net flow, price movement)

Decision guidelines:
  - Price moving favorably + sustained inflow -> hold
  - Price stagnant + long hold time + far from expiry -> consider closing to free capital
  - Large opposing flow detected -> new information likely, consider closing
  - Profitable + starting to retreat -> tighten stop-loss or close to lock in
  - Near expiry (< 30 min) + direction unclear -> close

Output:
{
  "positions": [
    {
      "signal_id": "xxx",
      "action": "close" | "hold" | "adjust_sl_tp",
      "new_stop_loss_pct": 0.03,
      "new_take_profit_pct": 0.15,
      "reasoning": "..."
    }
  ]
}
```

### 6.3 Coordinator Prompt (Upgraded)

```
Role: You are the risk manager for a Polymarket trading portfolio.

Core concerns:
  - Is total exposure too high (too much capital locked in unsettled markets)?
  - Are multiple positions correlated to the same event (correlation risk)?
  - Are any positions stagnant and tying up capital?
  - Has daily/weekly P&L hit risk control thresholds?

Input:
  - Account state (balance, total positions, daily P&L, weekly P&L)
  - All positions summary
  - Recent trading activity
  - Circuit breaker status

Decision:
  - Too many correlated market positions -> emergency_close the weaker one
  - Daily loss exceeds threshold -> pause_new_entry
  - Total exposure exceeds X% of balance -> pause_new_entry
  - Recovery to normal -> resume_entry

Output: (actions format as defined in Section 3)
```

### 6.4 Trading Modes

| Mode | Confidence Threshold | Edge Threshold | Max Positions | Use Case |
|------|---------------------|----------------|---------------|----------|
| `conservative` | 0.75 | 0.10 | 3 | High-certainty signals only |
| `balanced` | 0.65 | 0.06 | 5 | Default |
| `aggressive` | 0.55 | 0.04 | 8 | More market participation |

Trading mode affects system prompt parameters for all agents.

### 6.5 Custom Prompt

Users can add a custom prompt supplement in Settings, appended to each agent's system prompt. This allows users to inject domain knowledge or personal trading rules without modifying code.

### Configuration

```typescript
interface PromptConfig {
  tradingMode: "conservative" | "balanced" | "aggressive";  // Default "balanced"
  customPrompt?: string;          // User-defined supplement, appended to system prompts
  minConfidence: number;          // Derived from trading mode, user can override
  minEdge: number;                // Derived from trading mode, user can override
}
```

---

## 7. Exit System Design

### Key Constraint

Polymarket CLOB has **no conditional orders** (no stop-loss or take-profit order types). All exit logic must be implemented client-side.

### Exit Check Pipeline (per price tick)

```
price tick arrives
    |
    v
evaluateExit(position, currentPrice)
    |
    |-- Check 1: Expiry Safety (reason: "E")
    |   Exit if: timeToResolve <= expirySafetyBufferSec (default 300s)
    |
    |-- Check 2: Stop-Loss (reason: "A_SL")
    |   Normal: stopLossPctNormal (default 7%)
    |   Late stage (<30 min): stopLossPctLateStage (default 3%)
    |
    |-- Check 3: Take-Profit (reason: "A_TP")
    |   Exit if: profitDelta >= takeProfitPct (default 10%)
    |   Note: takeProfitPct may be AI-suggested per position
    |
    |-- Check 4: Drawdown Guard (reason: "DRAWDOWN_GUARD")  [NEW]
    |   Exit if: pnl > minProfitPct AND drawdownFromPeak >= maxDrawdownFromPeak
    |
    |-- Check 5: Time Cutoff (reason: "C")
    |   Exit if: holdingDuration >= maxHoldingSec (default 4 hours)
    |
    +-- Check 6: Reverse Signal (reason: "D")
        Exit if: opposite direction trigger fires for same market

AI-driven exits (async, periodic):
    |-- AI Position Evaluator (every 3 min) -> reason: "AI_EXIT"
    +-- Coordinator emergency (every 30 min) -> reason: "COORD_EMERGENCY"
```

### SL/TP Values

- Default values come from global config per trading mode
- AI Analyzer can **suggest** per-position values at entry time
- AI Position Evaluator can **adjust** values during holding
- All are local monitoring thresholds, not exchange orders

### Reliability Safeguards

Since there are no exchange-level SL/TP orders to protect positions if our process goes down:

| Risk | Mitigation |
|------|------------|
| Process crash | Electron process guardian + auto-restart on crash |
| Network disconnect | Disconnect detection + re-evaluate all positions immediately on reconnect |
| Price gap between ticks | Use FOK market order for close, not limit |
| Low CLOB liquidity on close | FOK fails -> downgrade to FAK (partial fill) + retry remainder |

### Frontend Display

SL/TP values displayed as "Local Monitoring Thresholds" in UI. Clear indication that these are not exchange-level orders - positions are unprotected if the application is not running.

---

## 8. Frontend Configuration UI

All new settings exposed in Settings page, organized by module.

### 8.1 Trading Section (New)

| Setting | Control | Default |
|---------|---------|---------|
| Trading Mode | Toggle: Paper / Live | Paper |
| Wallet Private Key | Password input + save to keychain | - |
| Proxy Funder Address | Text input | - |
| Slippage Threshold | Slider 0.5%-5% | 2% |
| Max Slippage | Slider 1%-10% | 3% |
| Limit Order Timeout | Number input (seconds) | 60 |
| Trading Style | Select: conservative / balanced / aggressive | balanced |
| Custom Prompt | Textarea | empty |

### 8.2 AI Position Evaluator Section (New)

| Setting | Control | Default |
|---------|---------|---------|
| Enable AI Exit | Toggle | On |
| Evaluation Interval | Number input (seconds) | 180 |
| Model Selection | Dropdown (from connected providers) | Follow analyzer |

### 8.3 Coordinator Section (Enhanced)

| Setting | Control | Default |
|---------|---------|---------|
| Allow Actions | Toggle | On |
| Run Interval | Number input (minutes) | 30 |

### 8.4 Drawdown Guard Section (New)

| Setting | Control | Default |
|---------|---------|---------|
| Enable Drawdown Guard | Toggle | On |
| Min Profit Threshold | Slider 1%-20% | 5% |
| Max Drawdown from Peak | Slider 10%-80% | 40% |

### 8.5 Custom LLM Endpoints Section (New)

| Setting | Control | Default |
|---------|---------|---------|
| Endpoint List | Card list + "Add" button | Empty |
| Per endpoint | Name / URL / Key / Model / "Auto-discover" button | - |

---

## Summary of New Files and Changes

### New Files

| File | Package | Purpose |
|------|---------|---------|
| `clob-order-service.ts` | engine | Polymarket CLOB API wrapper |
| `live-filler.ts` | engine/executor | LiveFiller implementing OrderFiller interface |
| `order-filler.ts` | engine/executor | OrderFiller interface definition |
| `drawdown-guard.ts` | engine/executor | Drawdown monitoring logic |
| `position-evaluator.ts` | engine | AI position evaluation loop |
| `position-evaluator-runner.ts` | llm/runners | LLM runner for position evaluation |
| `position-evaluator-persona.ts` | llm/runners/personas | System prompt for position evaluator |
| `custom-openai-manager.ts` | llm | Manage multiple custom OpenAI endpoints |

### Modified Files

| File | Package | Changes |
|------|---------|---------|
| `executor.ts` | engine/executor | Extract OrderFiller interface, add AI_EXIT/COORD_EMERGENCY/DRAWDOWN_GUARD reasons |
| `exit-monitor.ts` | engine/executor | Add drawdown guard check |
| `analyzer.ts` (persona) | llm/runners/personas | Upgraded prompt with account context, fair value, edge |
| `risk-manager.ts` (persona) | llm/runners/personas | Add actions output format |
| `risk-mgr-runner.ts` | llm/runners | Parse and return actions from coordinator response |
| `coordinator.ts` | main | Execute coordinator actions (close, adjust, pause, resume) |
| `lifecycle.ts` | main | Boot position evaluator loop, load custom providers |
| `ipc.ts` | main | Add custom_openai connect/disconnect handlers |
| `types.ts` | llm | Add "position_evaluator" agent role, extend ProviderId |
| `registry.ts` | llm | Support dynamic provider registration for custom endpoints |
| `SettingsPage.tsx` | renderer | New UI sections for all configurations |
| `settings.ts` | renderer/stores | New config types and state management |
| `schema.ts` | engine/config | Add new config interfaces |
