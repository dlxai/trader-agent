"""
部分止盈服务 (Partial Exit Service)

分级锁定利润，支持多级止盈策略。当价格达到每一级目标时，
自动卖出对应比例的仓位，实现利润的阶梯式锁定。
"""

import logging
from typing import Dict, List, Optional, Any, Union, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

from config.settings import settings

logger = logging.getLogger(__name__)


class TokenType(Enum):
    """代币类型"""
    YES = "yes"
    NO = "no"


class ExitType(Enum):
    """出场类型"""
    PARTIAL = "partial"  # 部分出场
    FULL = "full"  # 完全出场


@dataclass
class TierConfig:
    """止盈档位配置"""
    tier: int  # 档位级别（1, 2, 3...）
    profit_target: float  # 利润目标（如 0.20 表示 20%）
    exit_ratio: float  # 出场比例（如 0.25 表示 25%）
    description: str = ""  # 描述

    def __post_init__(self):
        if not self.description:
            self.description = f"Tier {self.tier}: {self.profit_target:.0%} profit, exit {self.exit_ratio:.0%}"


@dataclass
class PartialExitConfig:
    """部分止盈配置"""
    enabled: bool = True
    tiers: List[TierConfig] = field(default_factory=list)
    slippage_tolerance: float = 0.02  # 滑价容忍度 2%
    max_retries: int = 3  # 最大重试次数
    retry_delay_ms: int = 1000  # 重试延迟（毫秒）

    def __post_init__(self):
        # 如果没有提供档位配置，使用默认的三级止盈
        if not self.tiers:
            self.tiers = [
                TierConfig(
                    tier=1,
                    profit_target=0.20,  # 20% 利润
                    exit_ratio=0.25,  # 卖出 25% 仓位
                    description="Tier 1: 20% profit, exit 25% position"
                ),
                TierConfig(
                    tier=2,
                    profit_target=0.40,  # 40% 利润
                    exit_ratio=0.35,  # 卖出 35% 仓位
                    description="Tier 2: 40% profit, exit 35% position"
                ),
                TierConfig(
                    tier=3,
                    profit_target=0.60,  # 60% 利润
                    exit_ratio=0.40,  # 卖出 40% 仓位
                    description="Tier 3: 60% profit, exit 40% position"
                ),
            ]


@dataclass
class Position:
    """持仓数据"""
    position_id: str
    token_id: str
    market_id: str
    token_type: TokenType  # YES or NO
    entry_price: float
    current_price: float = 0.0
    size: float = 0.0
    remaining_size: float = 0.0  # 剩余仓位
    side: str = "LONG"  # LONG or SHORT
    opened_at: datetime = field(default_factory=datetime.now)

    # 已触发的止盈档位
    triggered_tiers: Set[int] = field(default_factory=set)

    def __post_init__(self):
        if self.remaining_size == 0 and self.size > 0:
            self.remaining_size = self.size

    def update_price(self, new_price: float):
        """更新当前价格"""
        self.current_price = new_price

    def mark_tier_triggered(self, tier: int):
        """标记档位已触发"""
        self.triggered_tiers.add(tier)

    def is_tier_triggered(self, tier: int) -> bool:
        """检查档位是否已触发"""
        return tier in self.triggered_tiers

    def update_remaining_size(self, exit_size: float):
        """更新剩余仓位"""
        self.remaining_size = max(0.0, self.remaining_size - exit_size)

    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏（以代币计价）"""
        if self.token_type == TokenType.YES:
            return (self.current_price - self.entry_price) * self.remaining_size
        else:  # NO token
            return (self.entry_price - self.current_price) * self.remaining_size

    @property
    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        if self.token_type == TokenType.YES:
            return (self.current_price - self.entry_price) / self.entry_price
        else:  # NO token
            return (self.entry_price - self.current_price) / self.entry_price

    @property
    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.unrealized_pnl_pct > 0

    @property
    def total_exit_ratio(self) -> float:
        """总出场比例"""
        if self.size == 0:
            return 0.0
        return (self.size - self.remaining_size) / self.size


@dataclass
class PartialExitTrigger:
    """部分止盈触发信号"""
    position_id: str
    token_id: str
    tier: int  # 触发的档位
    profit_target: float  # 利润目标
    profit_pct: float  # 当前利润百分比
    exit_ratio: float  # 出场比例
    exit_size: float  # 出场数量
    entry_price: float
    current_price: float
    token_type: TokenType
    should_exit: bool = True
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "token_id": self.token_id,
            "tier": self.tier,
            "profit_target": self.profit_target,
            "profit_pct": self.profit_pct,
            "exit_ratio": self.exit_ratio,
            "exit_size": self.exit_size,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "token_type": self.token_type.value,
            "should_exit": self.should_exit,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PartialExitExecution:
    """部分止盈执行结果"""
    position_id: str
    tier: int
    success: bool
    order_id: Optional[str] = None
    exit_price: Optional[float] = None
    exit_size: float = 0.0
    profit_amount: float = 0.0  # 实现盈利金额
    profit_pct: float = 0.0  # 实现盈利百分比
    slippage: float = 0.0
    retry_count: int = 0
    error_message: Optional[str] = None
    remaining_size: float = 0.0  # 剩余仓位
    is_fully_exited: bool = False  # 是否完全出场
    executed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "tier": self.tier,
            "success": self.success,
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


class PartialExitService:
    """
    部分止盈服务

    分级锁定利润，支持多级止盈策略。当价格达到每一级目标时，
    自动卖出对应比例的仓位，实现利润的阶梯式锁定。

    默认三级止盈：
    - Tier 1: 20% 利润，卖出 25% 仓位
    - Tier 2: 40% 利润，卖出 35% 仓位
    - Tier 3: 60% 利润，卖出 40% 仓位
    """

    def __init__(
        self,
        order_manager: Any,
        config: Optional[PartialExitConfig] = None
    ):
        """
        初始化部分止盈服务

        Args:
            order_manager: OrderManager 实例
            config: 部分止盈配置
        """
        self.order_manager = order_manager
        self.config = config or PartialExitConfig()

        # 持仓跟踪
        self._positions: Dict[str, Position] = {}

        # 执行回调
        self._execution_callbacks: List[Callable[[PartialExitExecution], None]] = []

        # 统计
        self._trigger_count = 0
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0

        # 验证档位配置
        self._validate_tier_config()

        logger.info(
            f"Partial exit service initialized: "
            f"enabled={self.config.enabled}, "
            f"tiers={len(self.config.tiers)}"
        )

    def _validate_tier_config(self):
        """验证档位配置"""
        if not self.config.tiers:
            logger.warning("No tiers configured for partial exit service")
            return

        # 检查总出场比例
        total_exit_ratio = sum(tier.exit_ratio for tier in self.config.tiers)
        if total_exit_ratio > 1.0:
            logger.warning(
                f"Total exit ratio exceeds 100%: {total_exit_ratio:.0%}. "
                "This may cause over-selling."
            )

        # 检查利润目标是否递增
        for i in range(1, len(self.config.tiers)):
            if self.config.tiers[i].profit_target <= self.config.tiers[i-1].profit_target:
                logger.warning(
                    f"Tier {i+1} profit target ({self.config.tiers[i].profit_target:.0%}) "
                    f"should be higher than tier {i} ({self.config.tiers[i-1].profit_target:.0%})"
                )

    def register_execution_callback(self, callback: Callable[[PartialExitExecution], None]):
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
        添加持仓

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
            f"Added position {position_id} for partial exit: "
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
            logger.debug(f"Removed position {position_id}")
            return True
        return False

    def update_price(self, position_id: str, current_price: float) -> List[PartialExitTrigger]:
        """
        更新价格并检查是否触发部分止盈

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            List[PartialExitTrigger]: 触发的止盈信号列表
        """
        if not self.config.enabled:
            return []

        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return []

        # 更新价格
        position.update_price(current_price)

        # 计算当前利润百分比
        current_profit_pct = position.unrealized_pnl_pct

        # 检查各个档位
        triggers = []
        for tier_config in self.config.tiers:
            # 跳过已触发的档位
            if position.is_tier_triggered(tier_config.tier):
                continue

            # 检查是否达到利润目标
            if current_profit_pct >= tier_config.profit_target:
                # 计算出场数量
                exit_size = position.size * tier_config.exit_ratio

                # 确保不超过剩余仓位
                exit_size = min(exit_size, position.remaining_size)

                if exit_size > 0:
                    trigger = PartialExitTrigger(
                        position_id=position.position_id,
                        token_id=position.token_id,
                        tier=tier_config.tier,
                        profit_target=tier_config.profit_target,
                        profit_pct=current_profit_pct,
                        exit_ratio=tier_config.exit_ratio,
                        exit_size=exit_size,
                        entry_price=position.entry_price,
                        current_price=current_price,
                        token_type=position.token_type,
                        should_exit=True,
                        reason=f"Partial exit tier {tier_config.tier} triggered: "
                               f"profit {current_profit_pct:.2%} >= target {tier_config.profit_target:.2%}, "
                               f"exiting {tier_config.exit_ratio:.0%} of position"
                    )

                    triggers.append(trigger)
                    position.mark_tier_triggered(tier_config.tier)
                    self._trigger_count += 1

                    logger.info(
                        f"Partial exit tier {tier_config.tier} triggered for {position_id}: "
                        f"profit={current_profit_pct:.2%}, exit_size={exit_size:.4f}"
                    )

        return triggers

    async def execute_partial_exit(
        self,
        trigger: PartialExitTrigger,
        **kwargs
    ) -> PartialExitExecution:
        """
        执行部分止盈平仓

        Args:
            trigger: 部分止盈触发信号
            **kwargs: 额外参数传递给 order_manager

        Returns:
            PartialExitExecution: 执行结果
        """
        self._execution_count += 1
        position_id = trigger.position_id
        tier = trigger.tier

        # 获取持仓
        position = self._positions.get(position_id)
        if not position:
            logger.error(f"Position not found for execution: {position_id}")
            self._failure_count += 1
            return PartialExitExecution(
                position_id=position_id,
                tier=tier,
                success=False,
                error_message=f"Position not found: {position_id}"
            )

        # 检查剩余仓位
        if position.remaining_size <= 0:
            logger.warning(f"Position {position_id} has no remaining size")
            self._failure_count += 1
            return PartialExitExecution(
                position_id=position_id,
                tier=tier,
                success=False,
                error_message="No remaining size to exit"
            )

        # 计算出场数量
        exit_size = min(trigger.exit_size, position.remaining_size)

        # 计算预期盈利
        entry_price = position.entry_price
        current_price = trigger.current_price

        if position.token_type == TokenType.YES:
            expected_profit_pct = (current_price - entry_price) / entry_price
        else:
            expected_profit_pct = (entry_price - current_price) / entry_price

        expected_profit_amount = expected_profit_pct * entry_price * exit_size

        # 重试逻辑
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                # 调用 OrderManager 创建市价单平仓
                execution = await self._place_market_order(
                    position=position,
                    trigger=trigger,
                    exit_size=exit_size,
                    attempt=attempt,
                    expected_profit_pct=expected_profit_pct,
                    expected_profit_amount=expected_profit_amount,
                    **kwargs
                )

                if execution.success:
                    self._success_count += 1

                    # 更新剩余仓位
                    position.update_remaining_size(exit_size)

                    # 检查是否完全出场
                    if position.remaining_size <= 0.001:  # 考虑浮点精度
                        execution.is_fully_exited = True
                        self.remove_position(position_id)
                        logger.info(
                            f"Position {position_id} fully exited after tier {tier}"
                        )

                    logger.info(
                        f"Partial exit tier {tier} executed successfully for {position_id}: "
                        f"order_id={execution.order_id}, "
                        f"exit_price={execution.exit_price:.4f}, "
                        f"profit={execution.profit_pct:.2%}, "
                        f"remaining={position.remaining_size:.4f}"
                    )
                else:
                    self._failure_count += 1
                    logger.error(
                        f"Partial exit tier {tier} execution failed for {position_id}: "
                        f"{execution.error_message}"
                    )

                # 触发回调
                self._notify_execution_callbacks(execution)

                return execution

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Partial exit tier {tier} execution attempt {attempt + 1} failed for {position_id}: {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await self._sleep(self.config.retry_delay_ms / 1000)

        # 所有重试都失败
        self._failure_count += 1
        logger.error(
            f"Partial exit tier {tier} execution failed after {self.config.max_retries} attempts for {position_id}"
        )

        execution = PartialExitExecution(
            position_id=position_id,
            tier=tier,
            success=False,
            retry_count=self.config.max_retries,
            error_message=last_error or f"Failed after {self.config.max_retries} attempts"
        )

        self._notify_execution_callbacks(execution)
        return execution

    async def _place_market_order(
        self,
        position: Position,
        trigger: PartialExitTrigger,
        exit_size: float,
        attempt: int,
        expected_profit_pct: float,
        expected_profit_amount: float,
        **kwargs
    ) -> PartialExitExecution:
        """
        下市价单平仓

        Args:
            position: 持仓数据
            trigger: 触发信号
            exit_size: 出场数量
            attempt: 当前重试次数
            expected_profit_pct: 预期盈利百分比
            expected_profit_amount: 预期盈利金额
            **kwargs: 额外参数

        Returns:
            PartialExitExecution: 执行结果
        """
        position_id = position.position_id
        tier = trigger.tier

        try:
            # 确定订单方向
            # 平仓方向与持仓方向相反
            if position.side == "LONG":
                from ..polymarket.order_manager import OrderSide
                order_side = OrderSide.SELL
            else:
                from ..polymarket.order_manager import OrderSide
                order_side = OrderSide.BUY

            # 创建市价单参数
            from ..polymarket.order_manager import OrderParams, OrderType
            order_params = OrderParams(
                token_id=position.token_id,
                side=order_side,
                size=exit_size,
                price=None,  # 市价单
                order_type=OrderType.MARKET,
                client_order_id=f"partial_exit_tier{tier}_{position_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )

            # 调用 OrderManager 创建订单
            if hasattr(self.order_manager, 'create_order'):
                result = await self.order_manager.create_order(order_params)
            else:
                # 如果 order_manager 不支持异步 create_order，使用同步方法
                import asyncio
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._sync_create_order(order_params)
                )

            if result.success:
                # 计算滑价
                exit_price = result.avg_fill_price or trigger.current_price
                expected_price = trigger.current_price
                slippage = abs(exit_price - expected_price) / expected_price if expected_price > 0 else 0

                # 计算实际盈利
                profit_pct = expected_profit_pct - (slippage if exit_price < expected_price else 0)
                profit_amount = expected_profit_amount * (1 - slippage) if slippage < 1 else 0

                # 检查滑价是否超过容忍度
                if slippage > self.config.slippage_tolerance:
                    logger.warning(
                        f"High slippage detected for {position_id} tier {tier}: "
                        f"{slippage:.2%} > {self.config.slippage_tolerance:.2%}"
                    )

                return PartialExitExecution(
                    position_id=position_id,
                    tier=tier,
                    success=True,
                    order_id=result.order_id,
                    exit_price=exit_price,
                    exit_size=exit_size,
                    profit_amount=profit_amount,
                    profit_pct=profit_pct,
                    slippage=slippage,
                    retry_count=attempt,
                    remaining_size=position.remaining_size - exit_size
                )
            else:
                return PartialExitExecution(
                    position_id=position_id,
                    tier=tier,
                    success=False,
                    retry_count=attempt,
                    error_message=result.error_message or "Order creation failed"
                )

        except Exception as e:
            logger.error(f"Error placing market order for {position_id} tier {tier}: {e}")
            return PartialExitExecution(
                position_id=position_id,
                tier=tier,
                success=False,
                retry_count=attempt,
                error_message=str(e)
            )

    def _sync_create_order(self, order_params) -> Any:
        """同步创建订单（用于在线程池中执行）"""
        raise NotImplementedError(
            "Synchronous order creation not supported. "
            "Please use an async OrderManager."
        )

    async def _sleep(self, seconds: float):
        """异步睡眠"""
        import asyncio
        await asyncio.sleep(seconds)

    def _notify_execution_callbacks(self, execution: PartialExitExecution):
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

    def update_config(self, config: PartialExitConfig):
        """更新配置"""
        self.config = config
        self._validate_tier_config()
        logger.info(f"Updated partial exit config: tiers={len(config.tiers)}, enabled={config.enabled}")

    def reset_position_tiers(self, position_id: str) -> bool:
        """
        重置持仓的档位状态

        Args:
            position_id: 持仓 ID

        Returns:
            bool: 是否成功重置
        """
        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found for reset: {position_id}")
            return False

        # 重置已触发档位
        position.triggered_tiers.clear()

        # 重置剩余仓位
        position.remaining_size = position.size

        logger.info(f"Reset tiers for position {position_id}")

        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "enabled": self.config.enabled,
            "tiers_count": len(self.config.tiers),
            "positions_count": len(self._positions),
            "trigger_count": self._trigger_count,
            "execution_count": self._execution_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": self._success_count / self._execution_count if self._execution_count > 0 else 0.0,
            "tiers_config": [
                {
                    "tier": t.tier,
                    "profit_target": t.profit_target,
                    "exit_ratio": t.exit_ratio,
                    "description": t.description
                }
                for t in self.config.tiers
            ]
        }


# 便捷函数

def create_default_partial_exit_service(
    order_manager: Any,
    **kwargs
) -> PartialExitService:
    """
    创建默认配置的部分止盈服务

    Args:
        order_manager: OrderManager 实例
        **kwargs: 其他配置参数

    Returns:
        PartialExitService: 部分止盈服务
    """
    config = PartialExitConfig(
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return PartialExitService(order_manager=order_manager, config=config)


def create_custom_partial_exit_service(
    order_manager: Any,
    tiers: List[TierConfig],
    **kwargs
) -> PartialExitService:
    """
    创建自定义档位的部分止盈服务

    Args:
        order_manager: OrderManager 实例
        tiers: 自定义档位配置列表
        **kwargs: 其他配置参数

    Returns:
        PartialExitService: 部分止盈服务
    """
    config = PartialExitConfig(
        tiers=tiers,
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return PartialExitService(order_manager=order_manager, config=config)
