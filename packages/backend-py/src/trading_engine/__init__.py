"""Trading engine package.

This package implements the trading engine architecture.

================================================================================
SIGNAL PIPELINE - Complete filtering flow (top to bottom)
================================================================================

WS Raw Data (Polymarket trades/orders/book)
    |
    v
Layer 0: DataIntegrityLayer
    - Timestamp validation, dedup, reorder
    - No rejection; only cleaning
    |
    v
Layer 1: InfraFilter (SignalFilter)
    - Price range:  min_price <= yes_price <= max_price
    - Dead zone:    reject if dead_zone_enabled and price in [dead_zone_min, dead_zone_max]
    - Keywords:     reject if market name contains keywords_exclude (e.g. 'o/u', 'spread')
    - NOTE: Time-based filtering is NOT performed here (delegated to ExpiryPolicy)
    |
    v
Activity Pre-filter (60s window)
    - Skip if unique_traders < 2 AND abs(netflow) < 50
    - Purpose: drop cold markets before expensive checks
    |
    v
Layer 2: EntryConditionValidator
    - Price validity
    - Liquidity:     available_liquidity >= min_liquidity (default 1000 USD)
    - Volatility:    min_volatility <= volatility <= max_volatility
    - NOTE: Expiry checks are disabled by default (all timedelta fields are None).
      Time decisions are centralized in ExpiryPolicy to avoid conflicting defaults.
    |
    v
ExpiryPolicy (UNIFIED TIME GATE)
    - Reads strategy.filters config:
        min_hours_to_expiry
        max_days_to_expiry
        avoid_last_minutes_before_expiry
    - BLOCK rules:
        hours_to_expiry <= 0                         -> already resolved
        hours_to_expiry < min_hours_to_expiry        -> too early
        hours_to_expiry < avoid_minutes / 60         -> too close to settlement
        hours_to_expiry > max_days_to_expiry * 24    -> too far
    - This is the ONLY component that hard-rejects based on time.
    |
    v
Layer 3: TriggerChecker
    - Price change trigger: abs(new - old) / old >= price_change_threshold (default 5%)
    - Activity trigger: netflow >= tiered threshold (based on price band)
    - Cooldown: min_trigger_interval (default 5 min)
    - Sports strong-signal can bypass the AND gate
    |
    v
Layer 4: FactorEngine / BuyStrategy.evaluate()
    - Computes composite score from six dimensions:
        odds_bias        (25%)  - implied vs estimated probability
        time_decay       (15%)  - smooth scoring by urgency (NO hard rejection)
        orderbook        (20%)  - bid/ask imbalance
        capital_flow     (20%)  - smart money flow
        information_edge (10%)  - price-volume divergence
        sports_momentum  (15%)  - live score momentum
    - Output: STRONG_BUY / BUY / HOLD / PASS / BLOCKED
    |
    v
Layer 5: AI Analysis (optional, if provider_id is set)
    - LLM receives market summary + factor scores
    - Final approve / reject
    |
    v
OrderExecutor -> PositionTracker -> ExitEngine

================================================================================
ARCHITECTURAL PRINCIPLE: Centralized Expiry
================================================================================

Before this refactor, time filtering was scattered across three layers with
conflicting defaults:

    SignalFilter:           max_hours_to_expiry = 6          (reject > 6h)
    EntryCondition:         min_time_to_expiry = 24h         (reject < 24h)
    BuyStrategy:            max_time_to_expiry_days = 30     (score penalty)

Result: SignalFilter allowed <= 6h markets, but EntryCondition rejected
all < 24h markets -> DEADLOCK, zero signals.

After refactor:
    - SignalFilter and EntryCondition do NOT reject on time.
    - ExpiryPolicy is the single authority for time-based hard rejection.
    - BuyStrategy.time_decay only contributes to the composite score.
    - Strategy-specific time windows are configured in strategy.filters
      and interpreted by ExpiryPolicy.

================================================================================
Module map
================================================================================

- DataIntegrityLayer: Layer 0 - Timestamp validation, dedup, reorder
- InfraFilter:        Layer 1 - Data quality filtering
- EventNormalizer:    Layer 2 - Unified event format
- TemporalBuffer:     Layer 3 - Rolling windows per game
- FactorEngine:       Layer 4 - Factor computation
- ScoreAggregator:    Layer 5 - Score composition
- ExpiryPolicy:       Time gate - centralized expiry check
- StrategyManager:    Strategy lifecycle
- PositionTracker:    Position state machine
- RiskManager:        Risk management
"""

from .event_bus import EventBus, EventType
from .data_integrity import DataIntegrityLayer, CleanEvent
from .infra_filter import InfraFilter, FilterConfig
from .event_normalizer import EventNormalizer, NormalizedEvent
from .temporal_buffer import TemporalBuffer, GameBuffer, TimelineEntry
from .factor_engine import FactorEngine, FlowFactors, GameStateFactors, CrossFactors, AllFactors
from .score_aggregator import ScoreAggregator, ScoreConfig, CompositeScores
from .strategy_manager import StrategyManager, StrategyInstance, StrategyState, Decision
from .position_tracker import PositionTracker, Position, PositionStatus
from .risk_manager import RiskManager, RiskConfig, ApprovalResult
from .collector import DataCollector
from .analyzer import SignalAnalyzer
from .executor import OrderExecutor
from .reviewer import PerformanceReviewer
from .expiry_policy import ExpiryPolicy, ExpiryVerdict, ExpiryAction

__all__ = [
    # EventBus
    "EventBus",
    "EventType",
    # Layers 0-5
    "DataIntegrityLayer",
    "CleanEvent",
    "InfraFilter",
    "FilterConfig",
    "EventNormalizer",
    "NormalizedEvent",
    "TemporalBuffer",
    "GameBuffer",
    "TimelineEntry",
    "FactorEngine",
    "FlowFactors",
    "GameStateFactors",
    "CrossFactors",
    "AllFactors",
    "ScoreAggregator",
    "ScoreConfig",
    "CompositeScores",
    # ExpiryPolicy
    "ExpiryPolicy",
    "ExpiryVerdict",
    "ExpiryAction",
    # Core components
    "StrategyManager",
    "StrategyInstance",
    "StrategyState",
    "Decision",
    "PositionTracker",
    "Position",
    "PositionStatus",
    "RiskManager",
    "RiskConfig",
    "ApprovalResult",
    # Legacy
    "DataCollector",
    "SignalAnalyzer",
    "OrderExecutor",
    "PerformanceReviewer",
]
