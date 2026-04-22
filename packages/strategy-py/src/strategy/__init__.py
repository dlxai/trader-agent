"""
策略模块 - 包含交易决策和执行相关的组件

该模块提供了完整的交易策略实现，包括：
- 买入策略决策 (BuyStrategy)
- 执行引擎 (ExecutionEngine)
- 信号评估器 (SignalEvaluator)
- Polymarket专用信号 (PolymarketSignal)
- 活动分析器 (ActivityAnalyzer)
- 实时服务 (RealtimeService)
"""

# 买入策略决策
from .buy_strategy import (
    BuyStrategy,
    BuyStrategyConfig,
    BuyDecision,
    BuyDecisionOutput,
    SignalStrength,
    MarketContext,
    OddsBiasMetrics,
    TimeDecayMetrics,
    OrderbookPressureMetrics,
    CapitalFlowMetrics,
    InformationEdgeMetrics,
    RiskCheckResult,
)

# 执行引擎
from .execution_engine import (
    ExecutionEngine,
    ExecutionConfig,
    ExecutionReport,
    OrderType,
    OrderSide,
    OrderStatus,
    ExecutionStatus,
    OrderParams,
    OrderResult,
)

# 信号评估器
from .signal_evaluator import (
    SignalEvaluator,
    SignalEvaluationConfig,
    SignalQuality,
    SignalDirection,
    SignalRecord,
    SignalOutcome,
    SignalMetrics,
)

# 信号生成器
from .signal_generator import (
    SignalGenerator,
    Signal,
    SignalType,
    LayeredSignalPipeline,
)

# Polymarket专用信号
from .polymarket_signals import (
    BaseSignalGenerator,
    PolymarketSignal,
    MarketState,
    SignalType,
    SignalStrength,
    SignalDirection,
    OrderBookSnapshot,
    CapitalFlowMetrics,
    EventInfo,
    OddsBiasSignalGenerator,
    TimeDecaySignalGenerator,
    OrderbookPressureSignalGenerator,
    CapitalFlowSignalGenerator,
    InformationEdgeSignalGenerator,
    CompoundSignalGenerator,
)

# 活动分析器
from .activity_analyzer import (
    ActivityAnalyzer,
    MarketActivity,
    Anomaly,
    TraderProfile,
)

# 实时服务
from .realtime_service import (
    RealtimeService,
    EventEmitter,
    ProxyConfig,
    ProxyHelper,
    PolymarketError,
    ErrorCode,
    WebSocketTopic,
    MessageType,
)

# 入口条件
from .entry_condition import (
    EntryConditionValidator,
    EntryConditionConfig,
    EntryCheckResult,
    EntryValidationResult,
)

# 入口验证器
from .entry_validator import (
    EntryValidator,
    EntryValidationResult,
    EntryRejectionReason,
)

# 仓位大小
from .position_sizer import (
    PositionSizer,
    PositionSizerConfig,
    PositionSizingResult,
    Position,
    PortfolioState,
    SizingRecommendation,
    PositionSizingMethod,
    SizingStrategy,
    KellyCriterionStrategy,
    FixedRiskStrategy,
    ConfidenceWeightedStrategy,
)

# 资本流分析器
from .capital_flow_analyzer import (
    FlowDirection,
    SignalStrength,
    DecisionAction,
    TradeRecord,
    FlowMetrics,
    FlowSignal,
    DecisionResult,
    PerformanceMetrics,
    CapitalFlowCollector,
    FlowSignalCalculator,
    FlowAssistedDecision,
    FlowAnalytics,
    CapitalFlowAssistedExit,
)


__version__ = "1.0.0"

__all__ = [
    # Buy Strategy
    "BuyStrategy",
    "BuyStrategyConfig",
    "BuyDecision",
    "BuyDecisionOutput",
    "SignalStrength",
    "MarketContext",
    "OddsBiasMetrics",
    "TimeDecayMetrics",
    "OrderbookPressureMetrics",
    "CapitalFlowMetrics",
    "InformationEdgeMetrics",
    "RiskCheckResult",

    # Execution Engine
    "ExecutionEngine",
    "ExecutionConfig",
    "ExecutionReport",
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "ExecutionStatus",
    "OrderParams",
    "OrderResult",

    # Signal Evaluator
    "SignalEvaluator",
    "SignalEvaluationConfig",
    "SignalQuality",
    "SignalDirection",
    "SignalRecord",
    "SignalOutcome",
    "SignalMetrics",

    # Signal Generator
    "SignalGenerator",
    "Signal",
    "SignalType",
    "LayeredSignalPipeline",

    # Polymarket Signals
    "BaseSignalGenerator",
    "PolymarketSignal",
    "MarketState",
    "SignalStrength",
    "SignalDirection",
    "OrderBookSnapshot",
    "CapitalFlowMetrics",
    "EventInfo",
    "OddsBiasSignalGenerator",
    "TimeDecaySignalGenerator",
    "OrderbookPressureSignalGenerator",
    "CapitalFlowSignalGenerator",
    "InformationEdgeSignalGenerator",
    "CompoundSignalGenerator",

    # Activity Analyzer
    "ActivityAnalyzer",
    "MarketActivity",
    "Anomaly",
    "TraderProfile",

    # Realtime Service
    "RealtimeService",
    "EventEmitter",
    "ProxyConfig",
    "ProxyHelper",
    "PolymarketError",
    "ErrorCode",
    "WebSocketTopic",
    "MessageType",

    # Entry Condition
    "EntryConditionValidator",
    "EntryConditionConfig",
    "EntryCheckResult",
    "EntryValidationResult",

    # Entry Validator
    "EntryValidator",
    "EntryValidationResult",
    "EntryRejectionReason",

    # Position Sizer
    "PositionSizer",
    "PositionSizerConfig",
    "PositionSizingResult",
    "Position",
    "PortfolioState",
    "SizingRecommendation",
    "PositionSizingMethod",
    "SizingStrategy",
    "KellyCriterionStrategy",
    "FixedRiskStrategy",
    "ConfidenceWeightedStrategy",

    # Capital Flow Analyzer
    "FlowDirection",
    "DecisionAction",
    "TradeRecord",
    "FlowMetrics",
    "FlowSignal",
    "DecisionResult",
    "PerformanceMetrics",
    "CapitalFlowCollector",
    "FlowSignalCalculator",
    "FlowAssistedDecision",
    "FlowAnalytics",
    "CapitalFlowAssistedExit",
]
