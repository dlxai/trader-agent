"""Trading engine package.

This package implements the trading engine architecture:
- DataIntegrityLayer: Layer 0 - Timestamp validation, dedup, reorder
- InfraFilter: Layer 1 - Data quality filtering
- EventNormalizer: Layer 2 - Unified event format
- TemporalBuffer: Layer 3 - Rolling windows
- FactorEngine: Layer 4 - Factor computation
- ScoreAggregator: Layer 5 - Score composition
- StrategyManager: Strategy lifecycle
- PositionTracker: Position state machine
- RiskManager: Risk management
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
