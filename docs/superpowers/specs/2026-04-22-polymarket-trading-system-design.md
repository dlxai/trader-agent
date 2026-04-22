# Polymarket Sports Trading System - Architecture Design

**Version:** 1.0  
**Date:** 2026-04-22  
**Status:** Approved

---

## 1. Overview

### 1.1 System Purpose
Event-driven quantitative trading system for Polymarket sports prediction markets, combining real-time capital flow data (Activity WebSocket) and sports score data (Sports WebSocket) with LLM-powered signal analysis.

### 1.2 Core Principle
**Data → Factor → Score → Decision**

Strategies never read WebSocket directly. All data flows through standardized layers.

---

## 2. System Architecture

### 2.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Data Layer (Always Running)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Layer 0: Data Integrity                                                    │
│  ├── Timestamp validation                                                   │
│  ├── Duplicate removal (trade_id)                                           │
│  └── Order reordering                                                       │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 1: Infra Filter                                                      │
│  ├── min_trade_size: >= 10                                                  │
│  ├── min_liquidity: >= 1000                                                 │
│  ├── max_spread_percent: <= 5%                                               │
│  └── match_status: live/in_progress                                          │
│  ⚠️ Infrastructure only - no strategy preferences                            │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 2: Event Normalizer                                                 │
│  ├── ActivityWS + SportsWS → NormalizedEvent                                │
│  └── {market_id, game_id, timestamp, type, payload}                        │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 3: Temporal Buffer                                                   │
│  ├── GameBuffer                                                             │
│  │   ├── score_timeline                                                     │
│  │   ├── event_timeline                                                     │
│  │   └── trade_timeline                                                     │
│  └── Windows: rolling_30s, rolling_2m, rolling_5m                             │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 4: FactorEngine                                                      │
│  ├── FlowFactors (from trade_timeline)                                      │
│  ├── GameStateFactors (from score_timeline + event_timeline)                │
│  └── CrossFactors (multi-dimension combination)                             │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 5: ScoreAggregator                                                   │
│  └── FactorSnapshot: {raw_factors, normalized_factors, composite_scores}   │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 6: StrategyManager                                                    │
│  ├── StrategyPreFilter (strategy preferences)                                │
│  └── Entry/Hold/Exit Decision                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Score System

### 3.1 EdgeScore
**Type:** Relative Momentum Signal  
**Range:** [-1, 1]

```python
EdgeScore = Direction × Strength × Acceleration
```

| Component | Range | Description |
|-----------|-------|-------------|
| Direction | [-1, 1] | Trend direction: +1=YES strong, -1=NO strong |
| Strength | [0, 1] | Signal strength from factor agreement |
| Acceleration | [0, 1] | Momentum strengthening/decay |

**Time Decay:**
- When `time_pressure > 0.85`: `Strength *= 0.5`
- Reason: End-game momentum becomes "chase trap"

### 3.2 EV_Score
**Type:** Expected Value Deviation  
**Range:** [0, 1]

```python
EV_Score = LLM_EV × MarketDeviationScore
```

| Component | Weight | Description |
|-----------|--------|-------------|
| LLM_EV | 0.4 | LLM structural judgment |
| MarketDeviation | 0.6 | \|implied_prob - flow_prob\| |

### 3.3 RiskScore
**Type:** Risk Quality  
**Range:** [0, 1]

```python
RiskScore = max(V, S, T, L)
```

| Component | Weight | Description |
|-----------|--------|-------------|
| V_volatility | 0.25 | Volatility risk |
| S_spread | 0.25 | Spread risk |
| T_time_instability | 0.30 | Stage instability |
| L_latency | 0.20 | Data latency risk |

---

## 4. Factor Definitions

### 4.1 Flow Factors
*From trade_timeline*

| Factor | Formula | Range |
|--------|---------|-------|
| net_flow_rate | (BV - SV) / (BV + SV) | [-1, 1] |
| flow_acceleration | (NFR_now - NFR_avg) / \|NFR_avg\| | [-10, 10] |
| large_trade_density | large_trades / total_trades (window T) | [0, 1] |
| smart_money_score | profitable_large_trades / total_large_trades | [0, 1] |
| order_book_imbalance | (bid_vol - ask_vol) / (bid_vol + ask_vol) | [-1, 1] |

### 4.2 Game State Factors
*From score_timeline + event_timeline*

| Factor | Formula | Range |
|--------|---------|-------|
| score_gap_change_rate | (gap_now - gap_start) / \|gap_start\| | [-2, 2] |
| match_time_progress | elapsed_minutes / total_minutes | [0, 1] |
| key_event_trigger | 1 if event else 0 | {0, 1} |
| attack_pace_index | attack_count / expected_attacks | [0, 3] |
| score_deviation | \|actual - expected\| / expected | [0, 5] |

### 4.3 Cross Factors
*Multi-dimension combination*

| Factor | Formula | Range |
|--------|---------|-------|
| momentum_resonance | sign(flow_dir) × sign(score_dir) | [-1, 1] |
| sentiment_index | w1×NFR + w2×OCR + w3×SGCR + w4×API | [-1, 1] |
| event_flow_lag | t(flow_peak) - t(event) | [0, 120]s |

---

## 5. Decision Logic

### 5.1 Entry Conditions

```python
if abs(EdgeScore) > 0.4 \
   and EV_Score > 0.6 \
   and RiskScore < 0.5 \
   and sustained_confirm >= 3 snapshots:
    Entry
elif RiskScore > 0.8:
    Reject All
else:
    Hold
```

### 5.2 Sustained Confirmation
Avoid single snapshot spike triggers:

- **Min Snapshots:** 3 consecutive
- **Max Window:** 10 seconds
- **Direction Tolerance:** 0.1

### 5.3 Time Pressure Adjustment

```python
if time_pressure > 0.85:
    EdgeScore_Strength *= 0.5
    RiskScore += 0.2
```

---

## 6. Position Management

### 6.1 Position Lifecycle

```
Entry → PositionTracker.add() → PriceMonitor.subscribe() → Monitor Loop
                                                              │
                                                    ┌────────┴────────┐
                                                    ▼                 ▼
                                            Take Profit          Stop Loss
                                                    │                 │
                                                    └────────┬────────┘
                                                             ▼
                                                     ExecutionLayer.close()
                                                             │
                                                             ▼
                                                  OrderSyncer confirms
                                                             │
                                                             ▼
                                                   PositionTracker.remove()
                                                   PriceMonitor.unsubscribe()
```

### 6.2 Position Status Machine

```
OPEN ──→ CLOSING ──→ CLOSED
   │         │
   └─────────┴──→ ERROR
```

### 6.3 Exit Triggers

| Trigger | Condition |
|---------|-----------|
| Take Profit | price >= entry × (1 + tp_pct) |
| Stop Loss | price <= entry × (1 - sl_pct) |
| Timeout | time_held > max_hold_seconds |
| Time Pressure | time_pressure > 0.9 → tighten exits |

---

## 7. Data Sources

### 7.1 WebSocket Connections
- **Mode:** Global single connection per type
- **ActivityWS:** Capital flow data
- **SportsWS:** Real-time score data

### 7.2 Price Monitoring

```
WebSocket Price Update
         │
         ▼
on_price_update(token_id, price)
         │
         ▼
PositionTracker.get_by_token(token_id)
         │
         ▼
Check exit conditions
         │
         ├── Trigger → ExecutionLayer.close()
         │
         └── No trigger → Continue monitoring
```

### 7.3 Position Syncer
- **Frequency:** Every 60 seconds
- **Purpose:** Chain state verification (not primary source)
- **Role:** Exception detection, manual trade detection

---

## 8. Strategy Instance

### 8.1 State Machine

```
CREATED → RUNNING → PAUSED → STOPPED
              ↓          ↑
            ERROR ───────┘
```

### 8.2 Instance Components

```python
class StrategyInstance:
    strategy_id: str
    config: StrategyConfig
    
    # Temporal data
    windows: Dict[window_name, RollingWindow]
    address_scores: Dict[address, float]
    
    # Position state
    position: Optional[Position]
    
    # LLM state
    last_llm_call: datetime
    llm_cooldown: seconds
    
    # State
    state: State
```

---

## 9. Component Inventory

| Component | Responsibility |
|-----------|----------------|
| WebSocket Sources | Single connection, data ingestion |
| EventBus | Publish/subscribe, event distribution |
| DataIntegrity | Timestamp, dedup, reorder |
| InfraFilter | Quality filtering only |
| EventNormalizer | Unified event format |
| TemporalBuffer | Rolling windows, TTL cleanup |
| FactorEngine | Factor computation |
| ScoreAggregator | Score composition |
| StrategyManager | Instance lifecycle |
| RiskManager | Unified risk control |
| ExecutionLayer | Order execution |
| PositionTracker | Position state machine |
| PriceMonitor | Dynamic subscription |
| OrderSyncer | Chain order confirmation |

---

## 10. Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Global single WS connection | Resource efficiency, consistent data |
| 2 | Layer 6 strategy pre-filter | Strategy-specific preferences isolated |
| 3 | Price-triggered monitoring | No polling, minimal latency |
| 4 | Sustained confirmation | Avoid spike false signals |
| 5 | Chain verification for positions | Prevent inconsistency |
| 6 | Position status machine | Prevent duplicate close orders |
| 7 | Time decay on EdgeScore | Avoid end-game chase trap |

---

## 11. Implementation Notes

### 11.1 FactorSnapshot Structure

```python
@dataclass
class FactorSnapshot:
    market_id: str
    game_id: str
    timestamp: datetime
    
    raw_factors: Dict[str, float]
    normalized_factors: Dict[str, float]
    
    composite_scores: {
        edge_score: float,      # [-1, 1]
        ev_score: float,       # [0, 1]
        risk_score: float,     # [0, 1]
    }
    
    sustained_confirm: int
```

### 11.2 Event Types

```python
class EventType(Enum):
    # Data events
    TRADE_UPDATE = auto()
    SCORE_UPDATE = auto()
    
    # Factor events
    FACTOR_UPDATED = auto()
    
    # Position events
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    
    # Signal events
    SIGNAL_GENERATED = auto()
    SIGNAL_APPROVED = auto()
    SIGNAL_REJECTED = auto()
```

---

## 12. Out of Scope

- [ ] Multiple WS connections per wallet (future)
- [ ] Manual trading integration
- [ ] Backtesting framework
- [ ] Performance benchmarking

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-22 | Initial approved version |
