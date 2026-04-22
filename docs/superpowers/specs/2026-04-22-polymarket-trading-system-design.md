# Polymarket Trading System - Architecture Design

**Version:** 3.0
**Date:** 2026-04-22
**Status:** Approved

---

## 1. Overview

### 1.1 System Purpose
Multi-market-type quantitative trading system for Polymarket prediction markets, supporting:
- **Sports markets** (Type A: event-driven regime, Activity + Sports WS)
- **Flow-only markets** (Type B: flow-driven regime, Activity only)

### 1.2 Core Principle
**Data → Factor → Score → Decision**

Strategies never read WebSocket directly. All data flows through standardized layers.

### 1.3 Key Innovation
**Two-Type Market System** - Markets are classified by data availability:
- Type A (Sports): Has Sports WebSocket data
- Type B (Flow-only): Activity WebSocket only

**IMPORTANT:** Never apply sports-specific factors to non-sports markets.

---

## 2. Market Classification

### 2.1 Two Market Types

| Type | Name | Data Sources | Regime | Examples |
|------|------|-------------|--------|----------|
| **Type A** | Sports | Activity + Sports WS | Event-driven | NBA, UCL, NFL, UFC, Tennis |
| **Type B** | Flow-only | Activity WS only | Flow-driven | Politics, Crypto, Economics, Weather |

### 2.2 Sports Subcategories (Type A)

```
Sports Markets (Activity + Sports WS)
─────────────────────────────────────
├─ NBA / Basketball
├─ UCL / Soccer / Football
├─ NFL / Football
├─ NHL / Hockey
├─ UFC / MMA / Boxing
├─ Tennis
├─ Cricket
├─ Baseball / MLB
├─ Rugby
├─ Golf
├─ Formula 1 / Racing
├─ Esports
└─ Other Sports
```

### 2.3 Flow-only Subcategories (Type B)

```
Flow-only Markets (Activity WS only)
─────────────────────────────────────
├─ Politics (Election, Policy)
├─ Crypto (BTC, ETH, Solana)
├─ Economics (CPI, Jobs, GDP, Fed)
├─ Weather (Hurricane, Temperature)
├─ Entertainment (Oscar, Emmy, Grammy)
└─ Other Events
```

---

## 3. System Architecture

### 3.1 Two-Type Architecture

```
Activity WS ──────────→ ALL markets
      │
Sports WS ────────────→ SPORTS only
      │
      ▼
┌─────────────────────┐
│  MarketResolver     │
└──────────┬──────────┘
           │
┌──────────┴──────────┐
▼                     ▼
Type A              Type B
Sports             Flow-only
           │
           ▼
┌─────────────────────────────┐
│  Dynamic FactorGraph        │
├─────────────────────────────┤
│  Type A: Flow-Score        │
│         Score Shock         │
│         Late Game Pressure  │
│                              │
│  Type B: Flow Momentum     │
│         Smart Money         │
│         LLM Sentiment       │
└─────────────────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Regime-Specific EdgeScore  │
├─────────────────────────────┤
│  Type A: Direction ×        │
│         Strength ×          │
│         Acceleration         │
│                              │
│  Type B: SmartMoneyFlow ×   │
│         NarrativeShift       │
└─────────────────────────────┘
```

---

## 4. MarketResolver

### 4.1 Sports Keywords Registry

```python
SPORTS_KEYWORDS = {
    "nba", "basketball",
    "ucl", "soccer", "football", "world cup", "euro",
    "nfl",
    "nhl", "hockey",
    "ufc", "mma", "boxing",
    "tennis",
    "cricket",
    "mlb", "baseball",
    "rugby",
    "golf",
    "formula1", "f1", "racing",
    "esports",
}
```

### 4.2 Resolution Logic

```python
class MarketResolver:
    def resolve(self, market: MarketInfo) -> MarketProfile:
        question_lower = market.question.lower()
        
        # Type A: Sports
        if self._is_sports(question_lower):
            return MarketProfile(
                market_id=market.id,
                category="sports",
                subcategory=self._detect_sports_subcategory(question_lower),
                regime="event-driven",
                data_dependencies=["activity", "sports_score"],
                schema="sports"
            )
        
        # Type B: Flow-only
        return MarketProfile(
            market_id=market.id,
            category=self._detect_other_category(question_lower),
            regime="flow-driven",
            data_dependencies=["activity"],
            schema="flow-only"
        )
    
    def _is_sports(self, question: str) -> bool:
        return any(kw in question for kw in SPORTS_KEYWORDS)
    
    def _detect_sports_subcategory(self, question: str) -> str:
        if "nba" in question or "basketball" in question:
            return "basketball"
        if "ucl" in question or "soccer" in question or "football" in question:
            return "soccer"
        if "nfl" in question:
            return "football"
        if "nhl" in question or "hockey" in question:
            return "hockey"
        if "ufc" in question or "mma" in question or "boxing" in question:
            return "mma"
        if "tennis" in question:
            return "tennis"
        if "cricket" in question:
            return "cricket"
        if "mlb" in question or "baseball" in question:
            return "baseball"
        if "rugby" in question:
            return "rugby"
        if "golf" in question:
            return "golf"
        if "formula1" in question or "f1" in question or "racing" in question:
            return "racing"
        if "esports" in question:
            return "esports"
        return "other"
    
    def _detect_other_category(self, question: str) -> str:
        politics = {"election", "president", "trump", "biden", "congress", "senate", "policy"}
        crypto = {"bitcoin", "btc", "ethereum", "eth", "solana", "crypto"}
        economics = {"cpi", "jobs", "gdp", "fed", "inflation", "unemployment"}
        weather = {"hurricane", "temperature", "snow", "weather", "storm", "rain"}
        entertainment = {"oscar", "emmy", "grammy", "award", "wins", "nominee"}
        
        if any(k in question for k in politics):
            return "politics"
        if any(k in question for k in crypto):
            return "crypto"
        if any(k in question for k in economics):
            return "economics"
        if any(k in question for k in weather):
            return "weather"
        if any(k in question for k in entertainment):
            return "entertainment"
        return "other"
```

---

## 5. Factor Schemas

### 5.1 Sports Schema (Type A)

```json
{
  "schema": "sports",
  "type": "event-driven",
  "data_dependencies": ["activity", "sports_score"],
  
  "factors": {
    "flow_score_alignment": {
      "formula": "sign(net_flow) × sign(score_gap_change)",
      "range": [-1, 1]
    },
    "shock_response": {
      "formula": "flow_acceleration following score_change",
      "range": [0, 1]
    },
    "late_game_pressure": {
      "formula": "time_progress > 0.85 ? 1 : 0",
      "range": [0, 1]
    }
  },
  
  "edge_score": {
    "formula": "Direction × Strength × Acceleration",
    "time_decay": {"threshold": 0.85, "action": "Strength *= 0.5"}
  }
}
```

### 5.2 Flow-only Schema (Type B)

```json
{
  "schema": "flow-only",
  "type": "flow-driven",
  "data_dependencies": ["activity"],
  
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
      "formula": "LLM(narrative).direction",
      "range": [-1, 1]
    }
  },
  
  "edge_score": {
    "formula": "SmartMoneyFlow × NarrativeShift"
  }
}
```

---

## 6. EdgeScore Definitions

| Type | Formula | Range |
|------|---------|-------|
| Type A (Sports) | `Direction × Strength × Acceleration` | [-1, 1] |
| Type B (Flow-only) | `SmartMoneyFlow × NarrativeShift` | [-1, 1] |

---

## 7. Decision Logic

```python
if abs(EdgeScore) > threshold \
   and EV_Score > 0.6 \
   and RiskScore < 0.5 \
   and sustained_confirm >= 3:
    Entry

# Threshold: Type A = 0.4, Type B = 0.35
```

---

## 8. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-22 | Initial version |
| 2.0 | 2026-04-22 | Market-Type Driven Architecture |
| 3.0 | 2026-04-22 | Two-Type System (Sports vs Flow-only), Sports subcategories |
