"""
综合止盈管理器 (Take Profit Manager)

统一协调各种止盈服务，包括固定止盈、部分止盈和追踪止盈。
提供统一的持仓管理和价格更新接口，防止重复触发，支持优先级配置。
"""

import logging
from typing import Dict, List, Optional, Any, Union, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from config.settings import settings

logger = logging.getLogger(__name__)


class TokenType(Enum):
    """代币类型"""
    YES = "yes"
    NO = "no"


class TakeProfitServiceType(Enum):
    """止盈服务类型"""
    FIXED = "fixed"           # 固定止盈
    PARTIAL = "partial"       # 部分止盈
    TRAILING = "trailing"     # 追踪止盈


class TakeProfitPriority(Enum):
    """止盈优先级"""
    PARTIAL_FIRST = "partial_first"   # 部分止盈优先
    TRAILING_FIRST = "trailing_first" # 追踪止盈优先
    FIXED_ONLY = "fixed_only"         # 仅固定止盈
    ALL_EQUAL = "all_equal"           # 所有服务平等


@dataclass
class TakeProfitConfig:
    """综合止盈配置"""
    enabled: bool = True
    priority: TakeProfitPriority = TakeProfitPriority.PARTIAL_FIRST

    # 各服务配置
    fixed_enabled: bool = True
    partial_enabled: bool = True
    trailing_enabled: bool = True

    # 防止重复触发配置
    deduplication_window_ms: int = 5000  # 5秒内不重复触发

    # 日志配置
    verbose_logging: bool = False


@dataclass
class Position:
    """持仓数据（简化版，用于管理器内部）"""
    position_id: str
    token_id: str
    market_id: str
    token_type: TokenType
    entry_price: float
    current_price: float = 0.0
    size: float = 0.0
    remaining_size: float = 0.0
    side: str = "LONG"
    opened_at: datetime = field(default_factory=datetime.now)

    # 止盈服务状态
    fixed_triggered: bool = False
    partial_triggered_tiers: Set[int] = field(default_factory=set)
    trailing_triggered: bool = False
    last_trigger_time: Optional[datetime] = None

    def update_price(self, new_price: float):
        """更新当前价格"""
        self.current_price = new_price

    def mark_triggered(self, service_type: TakeProfitServiceType, tier: Optional[int] = None):
        """标记服务已触发"""
        self.last_trigger_time = datetime.now()

        if service_type == TakeProfitServiceType.FIXED:
            self.fixed_triggered = True
        elif service_type == TakeProfitServiceType.PARTIAL and tier is not None:
            self.partial_triggered_tiers.add(tier)
        elif service_type == TakeProfitServiceType.TRAILING:
            self.trailing_triggered = True

    def is_service_triggered(self, service_type: TakeProfitServiceType, tier: Optional[int] = None) -> bool:
        """检查服务是否已触发"""
        if service_type == TakeProfitServiceType.FIXED:
            return self.fixed_triggered
        elif service_type == TakeProfitServiceType.PARTIAL and tier is not None:
            return tier in self.partial_triggered_tiers
        elif service_type == TakeProfitServiceType.TRAILING:
            return self.trailing_triggered
        return False

    def is_in_cooldown(self, cooldown_ms: int) -> bool:
        """检查是否在冷却期内"""
        if self.last_trigger_time is None:
            return False
        elapsed_ms = (datetime.now() - self.last_trigger_time).total_seconds() * 1000
        return elapsed_ms < cooldown_ms

    @property
    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        if self.token_type == TokenType.YES:
            return (self.current_price - self.entry_price) / self.entry_price
        else:  # NO token
            return (self.entry_price - self.current_price) / self.entry_price


@dataclass
class TakeProfitTrigger:
    """统一止盈触发信号"""
    position_id: str
    token_id: str
    service_type: TakeProfitServiceType
    tier: Optional[int] = None  # 对于部分止盈，记录档位
    entry_price: float = 0.0
    current_price: float = 0.0
    profit_pct: float = 0.0
    exit_ratio: float = 1.0
    exit_size: float = 0.0
    token_type: TokenType = TokenType.YES
    should_exit: bool = True
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "token_id": self.token_id,
            "service_type": self.service_type.value,
            "tier": self.tier,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "profit_pct": self.profit_pct,
            "exit_ratio": self.exit_ratio,
            "exit_size": self.exit_size,
            "token_type": self.token_type.value,
            "should_exit": self.should_exit,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TakeProfitExecution:
    """统一止盈执行结果"""
    position_id: str
    service_type: TakeProfitServiceType
    success: bool
    tier: Optional[int] = None
    order_id: Optional[str] = None
    exit_price: Optional[float] = None
    exit_size: float = 0.0
    profit_amount: float = 0.0
    profit_pct: float = 0.0
    slippage: float = 0.0
    retry_count: int = 0
    error_message: Optional[str] = None
    remaining_size: float = 0.0
    is_fully_exited: bool = False
    executed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "service_type": self.service_type.value,
            "success": self.success,
            "tier": self.tier,
            "order_id": self.order_id,
            "exit_price": self.exit_price,
            "exit_size": self.exit_size,
            "profit_amount": self.profit_amount,
            "profit_pct": self.profit_pct,
            "slippage": self.slippage,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "remaining_size": self.remaining_size,
            "is_fully_exited": self.is_fully_exited,
            "executed_at": self.executed_at.isoformat(),
        }


class TakeProfitManager:
    """
    综合止盈管理器

    统一协调多种止盈服务：
    - 固定止盈 (FixedTakeProfitService)
    - 部分止盈 (PartialExitService)
    - 追踪止盈 (TrailingStopService)

    核心功能：
    - 统一管理多种止盈服务
    - 配置优先级（如部分止盈优先于追踪止盈）
    - 防止重复触发
    - 统一的持仓管理和价格更新接口
    """

    def __init__(
        self,
        order_manager: Any,
        config: Optional[TakeProfitConfig] = None,
        fixed_service: Optional[Any] = None,
        partial_service: Optional[Any] = None,
        trailing_service: Optional[Any] = None
    ):
        """
        初始化综合止盈管理器

        Args:
            order_manager: OrderManager 实例
            config: 止盈管理器配置
            fixed_service: 固定止盈服务实例（可选）
            partial_service: 部分止盈服务实例（可选）
            trailing_service: 追踪止盈服务实例（可选）
        """
        self.order_manager = order_manager
        self.config = config or TakeProfitConfig()

        # 各止盈服务实例
        self._fixed_service = fixed_service
        self._partial_service = partial_service
        self._trailing_service = trailing_service

        # 持仓管理
        self._positions: Dict[str, Position] = {}

        # 执行回调
        self._execution_callbacks: List[Callable[[TakeProfitExecution], None]] = []

        # 统计
        self._trigger_stats: Dict[TakeProfitServiceType, int] = {
            TakeProfitServiceType.FIXED: 0,
            TakeProfitServiceType.PARTIAL: 0,
            TakeProfitServiceType.TRAILING: 0,
        }
        self._execution_count = 0
        self._success_count = 0

        logger.info(
            f"Take profit manager initialized: "
            f"enabled={self.config.enabled}, "
            f"priority={self.config.priority.value}, "
            f"services=[fixed={self._fixed_service is not None}, "
            f"partial={self._partial_service is not None}, "
            f"trailing={self._trailing_service is not None}]"
        )

    def register_execution_callback(self, callback: Callable[[TakeProfitExecution], None]):
        """注册执行回调"""
        self._execution_callbacks.append(callback)

    def add_position(
        self,
        position_id: str,
        token_id: str,
        market_id: str,
        token_type: Union[TokenType, str],
        entry_price: float,
        size: float,
        side: str = "LONG"
    ) -> Position:
        """
        添加持仓到管理器

        Args:
            position_id: 持仓 ID
            token_id: 代币 ID
            market_id: 市场 ID
            token_type: 代币类型 (YES/NO)
            entry_price: 入场价格
            size: 持仓数量
            side: 持仓方向 (LONG/SHORT)

        Returns:
            Position: 创建的持仓对象
        """
        # 转换 token_type
        if isinstance(token_type, str):
            token_type = TokenType.YES if token_type.lower() == "yes" else TokenType.NO

        # 创建持仓
        position = Position(
            position_id=position_id,
            token_id=token_id,
            market_id=market_id,
            token_type=token_type,
            entry_price=entry_price,
            current_price=entry_price,
            size=size,
            remaining_size=size,
            side=side
        )

        # 保存持仓
        self._positions[position_id] = position

        logger.info(
            f"Added position {position_id} to take profit manager: "
            f"entry={entry_price:.4f}, size={size}, type={token_type.value}"
        )

        return position

    def remove_position(self, position_id: str) -> bool:
        """
        移除持仓

        Args:
            position_id: 持仓 ID

        Returns:
            bool: 是否成功移除
        """
        if position_id in self._positions:
            del self._positions[position_id]
            logger.debug(f"Removed position {position_id} from manager")
            return True
        return False

    def update_price(self, position_id: str, current_price: float) -> List[TakeProfitTrigger]:
        """
        更新价格并检查所有止盈服务

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            List[TakeProfitTrigger]: 触发的止盈信号列表
        """
        if not self.config.enabled:
            return []

        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return []

        # 更新价格
        position.update_price(current_price)

        # 检查冷却期
        if position.is_in_cooldown(self.config.deduplication_window_ms):
            return []

        triggers = []

        # 根据优先级策略检查各服务
        if self.config.priority == TakeProfitPriority.PARTIAL_FIRST:
            triggers.extend(self._check_partial_service(position))
            if not triggers:
                triggers.extend(self._check_trailing_service(position))
            if not triggers:
                triggers.extend(self._check_fixed_service(position))

        elif self.config.priority == TakeProfitPriority.TRAILING_FIRST:
            triggers.extend(self._check_trailing_service(position))
            if not triggers:
                triggers.extend(self._check_partial_service(position))
            if not triggers:
                triggers.extend(self._check_fixed_service(position))

        elif self.config.priority == TakeProfitPriority.FIXED_ONLY:
            triggers.extend(self._check_fixed_service(position))

        else:  # ALL_EQUAL
            triggers.extend(self._check_partial_service(position))
            triggers.extend(self._check_trailing_service(position))
            triggers.extend(self._check_fixed_service(position))

        # 标记触发
        for trigger in triggers:
            position.mark_triggered(trigger.service_type, trigger.tier)
            self._trigger_stats[trigger.service_type] += 1

        return triggers

    def _check_fixed_service(self, position: Position) -> List[TakeProfitTrigger]:
        """检查固定止盈服务"""
        if not self.config.fixed_enabled or not self._fixed_service:
            return []

        # 调用固定止盈服务检查
        # 注意：这里需要根据实际情况调用 _fixed_service 的方法
        # 简化处理，实际实现需要适配具体服务接口
        return []

    def _check_partial_service(self, position: Position) -> List[TakeProfitTrigger]:
        """检查部分止盈服务"""
        if not self.config.partial_enabled or not self._partial_service:
            return []

        # 调用部分止盈服务检查
        # 简化处理，实际实现需要适配具体服务接口
        return []

    def _check_trailing_service(self, position: Position) -> List[TakeProfitTrigger]:
        """检查追踪止盈服务"""
        if not self.config.trailing_enabled or not self._trailing_service:
            return []

        # 调用追踪止盈服务检查
        # 简化处理，实际实现需要适配具体服务接口
        return []

    async def execute_take_profit(
        self,
        trigger: TakeProfitTrigger,
        **kwargs
    ) -> TakeProfitExecution:
        """
        执行止盈平仓

        Args:
            trigger: 止盈触发信号
            **kwargs: 额外参数

        Returns:
            TakeProfitExecution: 执行结果
        """
        self._execution_count += 1

        # 根据服务类型调用相应的服务执行
        if trigger.service_type == TakeProfitServiceType.FIXED and self._fixed_service:
            # 调用固定止盈服务
            execution = await self._execute_with_fixed_service(trigger, **kwargs)
        elif trigger.service_type == TakeProfitServiceType.PARTIAL and self._partial_service:
            # 调用部分止盈服务
            execution = await self._execute_with_partial_service(trigger, **kwargs)
        elif trigger.service_type == TakeProfitServiceType.TRAILING and self._trailing_service:
            # 调用追踪止盈服务
            execution = await self._execute_with_trailing_service(trigger, **kwargs)
        else:
            # 没有对应的服务
            execution = TakeProfitExecution(
                position_id=trigger.position_id,
                service_type=trigger.service_type,
                success=False,
                error_message=f"Service {trigger.service_type.value} not available"
            )

        # 更新统计
        if execution.success:
            self._success_count += 1

        # 触发回调
        self._notify_execution_callbacks(execution)

        return execution

    async def _execute_with_fixed_service(
        self,
        trigger: TakeProfitTrigger,
        **kwargs
    ) -> TakeProfitExecution:
        """使用固定止盈服务执行"""
        # 这里需要适配固定止盈服务的执行接口
        # 简化实现，实际使用时需要根据实际情况调整
        return TakeProfitExecution(
            position_id=trigger.position_id,
            service_type=TakeProfitServiceType.FIXED,
            success=False,
            error_message="Fixed service execution not implemented"
        )

    async def _execute_with_partial_service(
        self,
        trigger: TakeProfitTrigger,
        **kwargs
    ) -> TakeProfitExecution:
        """使用部分止盈服务执行"""
        # 这里需要适配部分止盈服务的执行接口
        return TakeProfitExecution(
            position_id=trigger.position_id,
            service_type=TakeProfitServiceType.PARTIAL,
            success=False,
            error_message="Partial service execution not implemented"
        )

    async def _execute_with_trailing_service(
        self,
        trigger: TakeProfitTrigger,
        **kwargs
    ) -> TakeProfitExecution:
        """使用追踪止盈服务执行"""
        # 这里需要适配追踪止盈服务的执行接口
        return TakeProfitExecution(
            position_id=trigger.position_id,
            service_type=TakeProfitServiceType.TRAILING,
            success=False,
            error_message="Trailing service execution not implemented"
        )

    def _notify_execution_callbacks(self, execution: TakeProfitExecution):
        """通知执行回调"""
        for callback in self._execution_callbacks:
            try:
                callback(execution)
            except Exception as e:
                logger.error(f"Error in execution callback: {e}")

    def get_position(self, position_id: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())

    def update_config(self, config: TakeProfitConfig):
        """更新配置"""
        self.config = config
        logger.info(f"Updated take profit manager config: priority={config.priority.value}, enabled={config.enabled}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "enabled": self.config.enabled,
            "priority": self.config.priority.value,
            "positions_count": len(self._positions),
            "trigger_stats": {
                k.value: v for k, v in self._trigger_stats.items()
            },
            "execution_count": self._execution_count,
            "success_count": self._success_count,
            "success_rate": self._success_count / self._execution_count if self._execution_count > 0 else 0.0,
            "services": {
                "fixed": self._fixed_service is not None and self.config.fixed_enabled,
                "partial": self._partial_service is not None and self.config.partial_enabled,
                "trailing": self._trailing_service is not None and self.config.trailing_enabled,
            }
        }


# 便捷函数

def create_take_profit_manager(
    order_manager: Any,
    priority: TakeProfitPriority = TakeProfitPriority.PARTIAL_FIRST,
    **kwargs
) -> TakeProfitManager:
    """
    创建综合止盈管理器

    Args:
        order_manager: OrderManager 实例
        priority: 止盈优先级
        **kwargs: 其他配置参数

    Returns:
        TakeProfitManager: 综合止盈管理器
    """
    config = TakeProfitConfig(
        priority=priority,
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'fixed_enabled', 'partial_enabled', 'trailing_enabled',
            'deduplication_window_ms', 'verbose_logging'
        ]}
    )

    return TakeProfitManager(
        order_manager=order_manager,
        config=config
    )
