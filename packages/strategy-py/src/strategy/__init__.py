"""
策略模块 - 包含交易决策和执行相关的组件

该模块提供了完整的交易策略实现，包括：
- 买入策略决策 (BuyStrategy)
- 执行引擎 (ExecutionEngine)
- 信号评估器 (SignalEvaluator)
- Polymarket专用信号 (PolymarketSignalGenerator)
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
    create_default_signal_evaluator,
    evaluate_signals_batch,
)

# 信号生成器
from .signal_generator import (
    SignalGenerator,
    BaseSignalGenerator,
    SignalData,
    SignalConfig,
)

# Polymarket专用信号
from .polymarket_signals import (
    PolymarketSignalGenerator,
    MarketCondition,
    SignalType,
    OddsMovement,
    VolumePattern,
)

# 活动分析器
from .activity_analyzer import (
    ActivityAnalyzer,
    MarketActivity,
    ActivityMetrics,
    AnomalyType,
    ActivityConfig,
)

# 实时服务
from .realtime_service import (
    RealtimeService,
    MarketDataStream,
    StreamConfig,
    DataProcessor,
)

# 入口条件
from .entry_condition import (
    EntryCondition,
    EntryConditionConfig,
    ConditionResult,
    ConditionType,
    MarketState,
)

# 入口验证器
from .entry_validator import (
    EntryValidator,
    EntryValidationConfig,
    ValidationResult,
    ValidationRule,
)

# 仓位大小
from .position_sizer import (
    PositionSizer,
    PositionSizeConfig,
    PositionSizeResult,
    KellyCriterion,
)

# 资本流分析器
from .capital_flow_analyzer import (
    CapitalFlowAnalyzer,
    CapitalFlowMetrics,
    FlowAnalyzerConfig,
    FlowPattern,
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
    "create_default_signal_evaluator",
    "evaluate_signals_batch",

    # Signal Generator
    "SignalGenerator",
    "BaseSignalGenerator",
    "SignalData",
    "SignalConfig",

    # Polymarket Signals
    "PolymarketSignalGenerator",
    "MarketCondition",
    "SignalType",
    "OddsMovement",
    "VolumePattern",

    # Activity Analyzer
    "ActivityAnalyzer",
    "MarketActivity",
    "ActivityMetrics",
    "AnomalyType",
    "ActivityConfig",

    # Realtime Service
    "RealtimeService",
    "MarketDataStream",
    "StreamConfig",
    "DataProcessor",

    # Entry Condition
    "EntryCondition",
    "EntryConditionConfig",
    "ConditionResult",
    "ConditionType",
    "MarketState",

    # Entry Validator
    "EntryValidator",
    "EntryValidationConfig",
    "ValidationResult",
    "ValidationRule",

    # Position Sizer
    "PositionSizer",
    "PositionSizeConfig",
    "PositionSizeResult",
    "KellyCriterion",

    # Capital Flow Analyzer
    "CapitalFlowAnalyzer",
    "CapitalFlowMetrics",
    "FlowAnalyzerConfig",
    "FlowPattern",
]
