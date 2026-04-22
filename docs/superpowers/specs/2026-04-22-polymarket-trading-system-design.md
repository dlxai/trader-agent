# Polymarket Trading System - Architecture Design

**Version:** 2.0
**Date:** 2026-04-22
**Status:** Approved

---

## 1. Overview

### 1.1 System Purpose
Multi-market-type quantitative trading system for Polymarket prediction markets, supporting:
- **Sports markets** (event-driven regime)
- **Political markets** (flow-driven + narrative regime)
- **Macro markets** (volatility-driven regime)
- **Crypto markets** (flow-driven regime)

### 1.2 Core Principle
**Data → Factor → Score → Decision**

Strategies never read WebSocket directly. All data flows through standardized layers.

### 1.3 Key Innovation
**Adaptive Factor Graph** - Different market types use different factor schemas. No hard-coded cross-market assumptions.

**IMPORTANT:** Never apply sports-specific factors (like "score_shock") to political markets. Each regime has its own EdgeScore definition.

---

## 2. System Architecture

### 2.1 Market-Type Driven Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MarketResolver                                       │
│  Determines market category from market metadata                              │
│  └── Returns MarketProfile with data_dependencies                            │
│                                    │                                         │
│                                    ▼                                         │
│  MarketProfile {                                                              │
│    market_id: "...",                                                          │
│    category: "sports | politics | macro | crypto",                          │
│    data_dependencies: ["activity", "sports_score", "llm"]                    │
│  }                                                                           │
│                                    │                                         │
│         ┌─────────────────────────┼─────────────────────────┐               │
│         ▼                         ▼                         ▼               │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐         │
│  │  Sports    │           │  Politics  │           │   Macro     │         │
│  │  Pipeline   │           │  Pipeline   │           │  Pipeline    │         │
│  └──────┬──────┘           └──────┬──────┘           └──────┬──────┘         │
│         │                         │                         │               │
│         ▼                         ▼                         ▼               │
│  Flow-Score Alignment      Flow Momentum            Volatility Cluster       │
│  Score Shock              Smart Money             Flow Spike                  │
│  Late Game Pressure        LLM Sentiment         Macro Sentiment            │
│  Price Delay vs Score                                                    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Dynamic FactorGraph                                │   │
│  │                                                                      │   │
│  │   factor_schema.json per market type:                                │   │
│  │   {                                                                  │   │
│  │     "sports": {                                                     │   │
│  │       "factors": ["flow_score_alignment", "shock_response"],         │   │
│  │       "weights": {...},                                             │   │
│  │       "llm_enabled": true                                           │   │
│  │     },                                                               │   │
│  │     "politics": {                                                    │   │
│  │       "factors": ["flow_momentum", "llm_sentiment"],               │   │
│  │       "weights": {...},                                              │   │
│  │       "llm_enabled": true                                           │   │
│  │     }                                                                │   │
│  │   }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                 Regime-Specific EdgeScore                              │   │
│  │                                                                      │   │
│  │   Sports:   EdgeScore = Direction × Strength × Acceleration          │   │
│  │   Politics: EdgeScore = SmartMoneyFlow × NarrativeShift              │   │
│  │   Macro:    EdgeScore = VolatilityCluster × FlowSpike                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  Strategy → RiskManager → Execution                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2.2 Market Regimes

| Regime | Market Types | Data Sources | EdgeScore Definition |
|--------|-------------|------------|---------------------|
| **Event-driven** | Sports | ActivityWS + SportsWS + LLM | Direction × Strength × Acceleration |
| **Flow-driven** | Politics, Crypto | ActivityWS + LLM | SmartMoneyFlow × NarrativeShift |
| **Volatility-driven** | Macro | ActivityWS + NewsFeed + LLM | VolatilityCluster × FlowSpike |

---

## 2.3 Layered Architecture (Base Pipeline)

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
│  └── match_status: live/in_progress (if applicable)                          │
│  ⚠️ Infrastructure only - no strategy preferences                            │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 2: Event Normalizer                                                 │
│  ├── All WS sources → NormalizedEvent                                      │
│  └── {market_id, game_id, timestamp, type, payload}                        │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 3: Temporal Buffer                                                   │
│  ├── GameBuffer (per market)                                               │
│  │   ├── score_timeline (if sports)                                        │
│  │   ├── event_timeline                                                   │
│  │   └── trade_timeline                                                   │
│  └── Windows: rolling_30s, rolling_2m, rolling_5m                         │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 4: MarketResolver                                                    │
│  ├── Determines market category from market metadata                        │
│  └── Returns MarketProfile with data_dependencies                           │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 5: Dynamic FactorGraph                                               │
│  ├── Loads factor_schema.json for market type                               │
│  ├── Computes only applicable factors (disables missing data sources)       │
│  └── Returns FactorGraph with regime-specific factors                       │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 6: Regime-Specific EdgeScore                                          │
│  ├── Sports: EdgeScore = Direction × Strength × Acceleration                │
│  ├── Politics: EdgeScore = SmartMoneyFlow × NarrativeShift                  │
│  └── Macro: EdgeScore = VolatilityCluster × FlowSpike                      │
│                                    │                                         │
│                                    ▼                                         │
│  Layer 7: StrategyManager                                                   │
│  └── Entry/Hold/Exit Decision                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. MarketProfile Definition

```json
{
  "market_profile": {
    "market_id": "0x1234...",
    "category": "sports | politics | macro | crypto",
    "data_dependencies": [
      "activity",
      "sports_score",
      "llm"
    ],
    "regime": "event-driven | flow-driven | volatility-driven"
  }
}
```

**Key Rule:** If a required data source is not in `data_dependencies`, all related factors are automatically disabled rather than erroring.

---

## 4. Factor Schemas (factor_schema.json)

### 4.1 Sports Schema

```json
{
  "sports": {
    "regime": "event-driven",
    "data_dependencies": ["activity", "sports_score", "llm"],
    "factors": {
      "flow_score_alignment": {
        "formula": "sign(net_flow) × sign(score_gap_change)",
        "range": [-1, 1]
      },
      "shock_response": {
        "formula": "flow_acceleration after key_event",
        "range": [0, 1]
      },
      "late_game_pressure": {
        "formula": "time_progress > 0.85 ? 1 : 0",
        "range": [0, 1]
      },
      "price_score_delay": {
        "formula": "correlation(price_change, score_change, lag=5s)",
        "range": [-1, 1]
      }
    },
    "edge_score": {
      "type": "event_momentum",
      "formula": "Direction × Strength × Acceleration",
      "weights": {
        "flow_score_alignment": 0.4,
        "shock_response": 0.2,
        "late_game_pressure": 0.2,
        "price_score_delay": 0.2
      }
    },
    "llm_enabled": true
  }
}
```

### 4.2 Politics Schema

```json
{
  "politics": {
    "regime": "flow-driven",
    "data_dependencies": ["activity", "llm"],
    "factors": {
      "flow_momentum": {
        "formula": "net_flow_rate × flow_acceleration",
        "range": [-1, 1]
      },
      "smart_money_clustering": {
        "formula": "large_trade_ratio × address_diversity",
        "range": [0, 1]
      },
      "llm_sentiment": {
        "formula": "LLM(political_narrative).direction",
        "range": [-1, 1]
      },
      "narrative_shift": {
        "formula": "|llm_sentiment_now - llm_sentiment_prev|",
        "range": [0, 1]
      }
    },
    "edge_score": {
      "type": "flow_narrative",
      "formula": "SmartMoneyFlow × NarrativeShift",
      "weights": {
        "flow_momentum": 0.35,
        "smart_money_clustering": 0.25,
        "llm_sentiment": 0.25,
        "narrative_shift": 0.15
      }
    },
    "llm_enabled": true
  }
}
```

### 4.3 Macro Schema

```json
{
  "macro": {
    "regime": "volatility-driven",
    "data_dependencies": ["activity", "macro_feed", "llm"],
    "factors": {
      "volatility_cluster": {
        "formula": "std(price_changes, window=60s)",
        "range": [0, 1]
      },
      "flow_spike": {
        "formula": "|net_flow_rate| > 2 × historical_avg",
        "range": [0, 1]
      },
      "macro_sentiment": {
        "formula": "LLM(macro_event).direction",
        "range": [-1, 1]
      },
      "cross_market_correlation": {
        "formula": "correlation(market_price, benchmark_price)",
        "range": [-1, 1]
      }
    },
    "edge_score": {
      "type": "volatility_momentum",
      "formula": "VolatilityCluster × FlowSpike",
      "weights": {
        "volatility_cluster": 0.3,
        "flow_spike": 0.3,
        "macro_sentiment": 0.25,
        "cross_market_correlation": 0.15
      }
    },
    "llm_enabled": true
  }
}
```

---

## 5. Core Score System

### 5.1 Regime-Specific EdgeScore

```python
# Sports (Event-driven)
EdgeScore_Sports = Direction × Strength × Acceleration
# Time decay: when time_pressure > 0.85, Strength *= 0.5

# Politics (Flow-driven)
EdgeScore_Politics = SmartMoneyFlow × NarrativeShift

# Macro (Volatility-driven)
EdgeScore_Macro = VolatilityCluster × FlowSpike
```

### 5.2 EV_Score
**Type:** Expected Value Deviation
**Range:** [0, 1]

```python
EV_Score = LLM_EV × MarketDeviationScore
```

| Component | Weight | Description |
|-----------|--------|-------------|
| LLM_EV | 0.4 | LLM structural judgment |
| MarketDeviation | 0.6 | \|implied_prob - flow_prob\| |

### 5.3 RiskScore
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

## 6. Decision Logic

### 6.1 Entry Conditions

```python
if abs(EdgeScore) > threshold \
   and EV_Score > 0.6 \
   and RiskScore < 0.5 \
   and sustained_confirm >= N snapshots:
    Entry
elif RiskScore > 0.8:
    Reject All
else:
    Hold
```

**Threshold varies by regime:**
- Sports: 0.4
- Politics: 0.35
- Macro: 0.3

### 6.2 Sustained Confirmation
Avoid single snapshot spike triggers:

- **Min Snapshots:** 3 consecutive
- **Max Window:** 10 seconds
- **Direction Tolerance:** 0.1

### 6.3 Time Pressure Adjustment

```python
if time_pressure > 0.85:
    EdgeScore_Strength *= 0.5
    RiskScore += 0.2
```

---

## 7. Position Management

### 7.1 Position Lifecycle

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

### 7.2 Position Status Machine

```
OPEN ──→ CLOSING ──→ CLOSED
   │         │
   └─────────┴──→ ERROR
```

### 7.3 Exit Triggers

| Trigger | Condition |
|---------|-----------|
| Take Profit | price >= entry × (1 + tp_pct) |
| Stop Loss | price <= entry × (1 - sl_pct) |
| Timeout | time_held > max_hold_seconds |
| Time Pressure | time_pressure > 0.9 → tighten exits |

---

## 8. Component Inventory

| Component | Responsibility |
|-----------|----------------|
| WebSocket Sources | Single connection per type, data ingestion |
| EventBus | Publish/subscribe, event distribution |
| DataIntegrity | Timestamp, dedup, reorder |
| InfraFilter | Quality filtering only |
| EventNormalizer | Unified event format |
| TemporalBuffer | Rolling windows per market, TTL cleanup |
| MarketResolver | Determines market category and regime |
| DynamicFactorGraph | Loads schema, computes regime-specific factors |
| RegimeEdgeScore | Computes regime-specific EdgeScore |
| ScoreAggregator | Score composition |
| StrategyManager | Instance lifecycle |
| RiskManager | Unified risk control |
| ExecutionLayer | Order execution |
| PositionTracker | Position state machine |
| PriceMonitor | Dynamic subscription, price-triggered checks |
| OrderSyncer | Chain order confirmation |

---

## 9. Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Market-type aware | Different markets need different factor graphs |
| 2 | Adaptive FactorGraph | Configurable per market type, not hard-coded |
| 3 | Regime-specific EdgeScore | Sports ≠ Politics ≠ Macro |
| 4 | Graceful factor disable | Missing data source ≠ error |
| 5 | Global single WS connection | Resource efficiency |
| 6 | Price-triggered monitoring | No polling, minimal latency |
| 7 | Sustained confirmation | Avoid spike false signals |
| 8 | Position status machine | Prevent duplicate close orders |

---

## 10. Out of Scope

- [ ] Multiple WS connections per wallet (future)
- [ ] Manual trading integration
- [ ] Backtesting framework
- [ ] Performance benchmarking
- [ ] Crypto-specific market schema (placeholder only)
- [ ] Options market schema (future)

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-22 | Initial version (sports only) |
| 2.0 | 2026-04-22 | Added Market-Type Driven Architecture, Adaptive FactorGraph, Regime-Specific EdgeScore |
