"""
风险管理模块
包含止损、止盈、价格保护等功能
"""

from .partial_exit_service import PartialExitService
from .trailing_stop_service import TrailingStopService
from .fixed_stop_service import FixedStopLossService
from .fixed_stop_loss import (
    FixedStopLossExecutor,
    FixedAmountStopLoss,
    FixedPercentageStopLoss,
    StopLossConfig,
    StopLossTrigger,
    StopLossExecution,
    Position,
    TokenType,
    StopLossType,
    create_fixed_amount_stop_loss,
    create_fixed_percentage_stop_loss,
)
from .fixed_take_profit import (
    FixedTakeProfitExecutor,
    FixedAmountTakeProfit,
    FixedPercentageTakeProfit,
    TakeProfitConfig,
    TakeProfitTrigger,
    TakeProfitExecution,
    Position as TakeProfitPosition,
    TokenType as TakeProfitTokenType,
    TakeProfitType,
    create_fixed_amount_take_profit,
    create_fixed_percentage_take_profit,
)
from .partial_exit import (
    PartialExitService as PartialExitServiceNew,
    TierConfig,
    PartialExitConfig,
    PartialExitTrigger,
    PartialExitExecution,
    Position as PartialExitPosition,
    TokenType as PartialExitTokenType,
    create_default_partial_exit_service,
    create_custom_partial_exit_service,
)
from .trailing_stop import (
    TrailingStopService as TrailingStopServiceNew,
    TrailingTier,
    TrailingStopConfig,
    TrailingStopTrigger,
    TrailingStopExecution,
    Position as TrailingStopPosition,
    TokenType as TrailingStopTokenType,
    create_default_trailing_stop_service,
    create_custom_trailing_stop_service,
)
from .take_profit_manager import (
    TakeProfitManager,
    TakeProfitConfig as ManagerConfig,
    TakeProfitTrigger as ManagerTrigger,
    TakeProfitExecution as ManagerExecution,
    TakeProfitServiceType,
    TakeProfitPriority,
    Position as ManagerPosition,
    TokenType as ManagerTokenType,
    create_take_profit_manager,
)
from .price_protection import PriceProtection, TokenConfusionDetector

__all__ = [
    # 原有止损相关
    "PartialExitService",
    "TrailingStopService",
    "FixedStopLossService",
    "FixedStopLossExecutor",
    "FixedAmountStopLoss",
    "FixedPercentageStopLoss",
    "StopLossConfig",
    "StopLossTrigger",
    "StopLossExecution",
    "Position",
    "TokenType",
    "StopLossType",
    "create_fixed_amount_stop_loss",
    "create_fixed_percentage_stop_loss",

    # 固定止盈
    "FixedTakeProfitExecutor",
    "FixedAmountTakeProfit",
    "FixedPercentageTakeProfit",
    "TakeProfitConfig",
    "TakeProfitTrigger",
    "TakeProfitExecution",
    "TakeProfitPosition",
    "TakeProfitTokenType",
    "TakeProfitType",
    "create_fixed_amount_take_profit",
    "create_fixed_percentage_take_profit",

    # 部分止盈（新版）
    "PartialExitServiceNew",
    "TierConfig",
    "PartialExitConfig",
    "PartialExitTrigger",
    "PartialExitExecution",
    "PartialExitPosition",
    "PartialExitTokenType",
    "create_default_partial_exit_service",
    "create_custom_partial_exit_service",

    # 追踪止盈（新版）
    "TrailingStopServiceNew",
    "TrailingTier",
    "TrailingStopConfig",
    "TrailingStopTrigger",
    "TrailingStopExecution",
    "TrailingStopPosition",
    "TrailingStopTokenType",
    "create_default_trailing_stop_service",
    "create_custom_trailing_stop_service",

    # 综合止盈管理器
    "TakeProfitManager",
    "ManagerConfig",
    "ManagerTrigger",
    "ManagerExecution",
    "TakeProfitServiceType",
    "TakeProfitPriority",
    "ManagerPosition",
    "ManagerTokenType",
    "create_take_profit_manager",

    # 价格保护
    "PriceProtection",
    "TokenConfusionDetector",
]
