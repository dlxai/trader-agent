"""
追踪止盈服务 (Trailing Stop Service)

动态调整止盈线，根据当前利润动态选择回撤档位。
记录最高价格，从最高点计算回撤，回撤触及档位线时触发平仓。
利润越高，允许的回撤越小（保护利润）。
"""

import logging
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from config.settings import settings

logger = logging.getLogger(__name__)


class TokenType(Enum):
    """代币类型"""
    YES = "yes"
    NO = "no"


@dataclass
class TrailingTier:
    """追踪止盈档位配置"""
    tier: int  # 档位级别
    min_profit: float  # 最小利润（如 0.05 表示 5%）
    max_profit: float  # 最大利润（如 0.10 表示 10%）
    drawdown: float  # 允许回撤百分比（如 0.15 表示 15%）
    description: str = ""  # 描述

    def __post_init__(self):
        if not self.description:
            self.description = (
                f"Tier {self.tier}: profit {self.min_profit:.0%}-{self.max_profit:.0%}, "
                f"drawdown {self.drawdown:.0%}"
            )

    def is_in_range(self, profit_pct: float) -> bool:
        """检查利润百分比是否在当前档位范围"""
        return self.min_profit <= profit_pct < self.max_profit


@dataclass
class TrailingStopConfig:
    """追踪止盈配置"""
    enabled: bool = True
    tiers: List[TrailingTier] = field(default_factory=list)
    slippage_tolerance: float = 0.02  # 滑价容忍度 2%
    max_retries: int = 3  # 最大重试次数
    retry_delay_ms: int = 1000  # 重试延迟（毫秒）

    def __post_init__(self):
        # 如果没有提供档位配置，使用默认的六级追踪止盈
        if not self.tiers:
            self.tiers = [
                TrailingTier(
                    tier=1,
                    min_profit=0.05,  # 5%
                    max_profit=0.10,  # 10%
                    drawdown=0.15,  # 15% 回撤
                    description="Tier 1: profit 5-10%, drawdown 15%"
                ),
                TrailingTier(
                    tier=2,
                    min_profit=0.10,  # 10%
                    max_profit=0.20,  # 20%
                    drawdown=0.12,  # 12% 回撤
                    description="Tier 2: profit 10-20%, drawdown 12%"
                ),
                TrailingTier(
                    tier=3,
                    min_profit=0.20,  # 20%
                    max_profit=0.35,  # 35%
                    drawdown=0.10,  # 10% 回撤
                    description="Tier 3: profit 20-35%, drawdown 10%"
                ),
                TrailingTier(
                    tier=4,
                    min_profit=0.35,  # 35%
                    max_profit=0.50,  # 50%
                    drawdown=0.08,  # 8% 回撤
                    description="Tier 4: profit 35-50%, drawdown 8%"
                ),
                TrailingTier(
                    tier=5,
                    min_profit=0.50,  # 50%
                    max_profit=0.75,  # 75%
                    drawdown=0.05,  # 5% 回撤
                    description="Tier 5: profit 50-75%, drawdown 5%"
                ),
                TrailingTier(
                    tier=6,
                    min_profit=0.75,  # 75%+
                    max_profit=float('inf'),  # 无上限
                    drawdown=0.03,  # 3% 回撤
                    description="Tier 6: profit 75%+, drawdown 3%"
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
    remaining_size: float = 0.0
    side: str = "LONG"
    opened_at: datetime = field(default_factory=datetime.now)

    # 追踪止盈相关
    highest_price: float = 0.0  # 最高价格
    current_tier: int = 0  # 当前档位
    trailing_stop_price: Optional[float] = None  # 追踪止损价格

    def __post_init__(self):
        if self.remaining_size == 0 and self.size > 0:
            self.remaining_size = self.size
        if self.highest_price == 0:
            self.highest_price = self.current_price if self.current_price > 0 else self.entry_price

    def update_price(self, new_price: float) -> bool:
        """
        更新当前价格

        Returns:
            bool: 是否创新高
        """
        self.current_price = new_price

        # 更新最高价格
        is_new_high = False
        if self.token_type == TokenType.YES:
            # YES token: 价格越高越好
            if new_price > self.highest_price:
                self.highest_price = new_price
                is_new_high = True
        else:
            # NO token: 价格越低越好
            if new_price < self.highest_price:
                self.highest_price = new_price
                is_new_high = True

        return is_new_high

    def update_tier(self, tier: int):
        """更新当前档位"""
        self.current_tier = tier

    def update_trailing_stop(self, stop_price: float):
        """更新追踪止损价格"""
        self.trailing_stop_price = stop_price

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


@dataclass
class TrailingStopTrigger:
    """追踪止盈触发信号"""
    position_id: str
    token_id: str
    tier: int  # 触发的档位
    entry_price: float
    current_price: float
    highest_price: float  # 最高价格
    trailing_stop_price: float  # 追踪止损价格
    drawdown: float  # 回撤百分比
    actual_drawdown: float  # 实际回撤
    token_type: TokenType
    should_exit: bool = True
    exit_ratio: float = 1.0  # 追踪止盈完全平仓
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "token_id": self.token_id,
            "tier": self.tier,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "highest_price": self.highest_price,
            "trailing_stop_price": self.trailing_stop_price,
            "drawdown": self.drawdown,
            "actual_drawdown": self.actual_drawdown,
            "token_type": self.token_type.value,
            "should_exit": self.should_exit,
            "exit_ratio": self.exit_ratio,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TrailingStopExecution:
    """追踪止盈执行结果"""
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
            "executed_at": self.executed_at.isoformat(),
        }


class TrailingStopService:
    """
    追踪止盈服务

    动态调整止盈线，根据当前利润动态选择回撤档位。
    记录最高价格，从最高点计算回撤，回撤触及档位线时触发平仓。
    利润越高，允许的回撤越小（保护利润）。

    默认六级追踪止盈：
    - Tier 1: 利润 5-10%, 回撤 15%
    - Tier 2: 利润 10-20%, 回撤 12%
    - Tier 3: 利润 20-35%, 回撤 10%
    - Tier 4: 利润 35-50%, 回撤 8%
    - Tier 5: 利润 50-75%, 回撤 5%
    - Tier 6: 利润 75%+, 回撤 3%
    """

    def __init__(
        self,
        order_manager: Any,
        config: Optional[TrailingStopConfig] = None
    ):
        """
        初始化追踪止盈服务

        Args:
            order_manager: OrderManager 实例
            config: 追踪止盈配置
        """
        self.order_manager = order_manager
        self.config = config or TrailingStopConfig()

        # 持仓跟踪
        self._positions: Dict[str, Position] = {}

        # 执行回调
        self._execution_callbacks: List[Callable[[TrailingStopExecution], None]] = []

        # 统计
        self._trigger_count = 0
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0

        logger.info(
            f"Trailing stop service initialized: "
            f"enabled={self.config.enabled}, "
            f"tiers={len(self.config.tiers)}"
        )

    def register_execution_callback(self, callback: Callable[[TrailingStopExecution], None]):
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
            f"Added position {position_id} for trailing stop: "
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

    def _get_tier_for_profit(self, profit_pct: float) -> Optional[TrailingTier]:
        """
        根据利润百分比获取对应的档位

        Args:
            profit_pct: 当前利润百分比

        Returns:
            TrailingTier: 对应的档位，如果没有找到则返回 None
        """
        if profit_pct <= 0:
            return None

        for tier in self.config.tiers:
            if tier.is_in_range(profit_pct):
                return tier

        # 检查是否超过最高档位
        if self.config.tiers and profit_pct >= self.config.tiers[-1].min_profit:
            return self.config.tiers[-1]

        return None

    def _calculate_trailing_stop_price(
        self,
        highest_price: float,
        drawdown: float,
        token_type: TokenType
    ) -> float:
        """
        计算追踪止损价格

        Args:
            highest_price: 最高价格
            drawdown: 回撤百分比
            token_type: 代币类型

        Returns:
            float: 追踪止损价格
        """
        if token_type == TokenType.YES:
            # YES token: 从最高价回撤
            stop_price = highest_price * (1 - drawdown)
            return max(0.0, stop_price)
        else:
            # NO token: 从最低价（最高价对于NO是低价）回撤
            stop_price = highest_price * (1 + drawdown)
            return min(1.0, stop_price)

    def update_price(self, position_id: str, current_price: float) -> Optional[TrailingStopTrigger]:
        """
        更新价格并检查是否触发追踪止盈

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            TrailingStopTrigger: 如果触发追踪止盈，否则 None
        """
        if not self.config.enabled:
            return None

        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return None

        # 更新价格并检查是否创新高
        is_new_high = position.update_price(current_price)

        # 计算当前利润百分比
        current_profit_pct = position.unrealized_pnl_pct

        # 如果当前未盈利，不检查追踪止盈
        if current_profit_pct <= 0:
            return None

        # 获取当前档位
        tier = self._get_tier_for_profit(current_profit_pct)

        if tier is None:
            return None

        # 如果档位升级，更新持仓档位
        if tier.tier > position.current_tier:
            position.update_tier(tier.tier)
            logger.info(
                f"Position {position_id} tier upgraded: {position.current_tier} -> {tier.tier}, "
                f"profit={current_profit_pct:.2%}"
            )

        # 计算追踪止损价格
        trailing_stop_price = self._calculate_trailing_stop_price(
            highest_price=position.highest_price,
            drawdown=tier.drawdown,
            token_type=position.token_type
        )

        # 更新持仓的追踪止损价格
        position.update_trailing_stop(trailing_stop_price)

        # 检查是否触发追踪止盈
        triggered = False
        actual_drawdown = 0.0

        if position.token_type == TokenType.YES:
            # YES token: 当前价格 <= 追踪止损价格时触发
            if current_price <= trailing_stop_price:
                triggered = True
                actual_drawdown = (position.highest_price - current_price) / position.highest_price
        else:
            # NO token: 当前价格 >= 追踪止损价格时触发
            if current_price >= trailing_stop_price:
                triggered = True
                actual_drawdown = (current_price - position.highest_price) / position.highest_price

        if triggered:
            self._trigger_count += 1

            logger.warning(
                f"Trailing stop triggered for {position_id} at tier {tier.tier}: "
                f"current={current_price:.4f}, "
                f"highest={position.highest_price:.4f}, "
                f"stop={trailing_stop_price:.4f}, "
                f"drawdown={actual_drawdown:.2%} (max allowed: {tier.drawdown:.2%})"
            )

            return TrailingStopTrigger(
                position_id=position.position_id,
                token_id=position.token_id,
                tier=tier.tier,
                entry_price=position.entry_price,
                current_price=current_price,
                highest_price=position.highest_price,
                trailing_stop_price=trailing_stop_price,
                drawdown=tier.drawdown,
                actual_drawdown=actual_drawdown,
                token_type=position.token_type,
                should_exit=True,
                exit_ratio=1.0,
                reason=f"Trailing stop tier {tier.tier} triggered: "
                       f"{position.token_type.value} price {current_price:.4f} "
                       f"breached trailing stop {trailing_stop_price:.4f} "
                       f"(drawdown: {actual_drawdown:.2%} > allowed: {tier.drawdown:.2%})"
            )

        return None

    async def execute_trailing_stop(
        self,
        trigger: TrailingStopTrigger,
        **kwargs
    ) -> 'TrailingStopExecution':
        """
        执行追踪止盈平仓

        Args:
            trigger: 追踪止盈触发信号
            **kwargs: 额外参数传递给 order_manager

        Returns:
            TrailingStopExecution: 执行结果
        """
        self._execution_count += 1
        position_id = trigger.position_id
        tier = trigger.tier

        # 获取持仓
        position = self._positions.get(position_id)
        if not position:
            logger.error(f"Position not found for execution: {position_id}")
            self._failure_count += 1
            return TrailingStopExecution(
                position_id=position_id,
                tier=tier,
                success=False,
                error_message=f"Position not found: {position_id}"
            )

        # 计算预期盈利
        entry_price = position.entry_price
        current_price = trigger.current_price

        if position.token_type == TokenType.YES:
            expected_profit_pct = (current_price - entry_price) / entry_price
        else:
            expected_profit_pct = (entry_price - current_price) / entry_price

        expected_profit_amount = expected_profit_pct * entry_price * position.remaining_size

        # 重试逻辑
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                # 调用 OrderManager 创建市价单平仓
                execution = await self._place_market_order(
                    position=position,
                    trigger=trigger,
                    attempt=attempt,
                    expected_profit_pct=expected_profit_pct,
                    expected_profit_amount=expected_profit_amount,
                    **kwargs
                )

                if execution.success:
                    self._success_count += 1

                    # 移除持仓
                    self.remove_position(position_id)

                    logger.info(
                        f"Trailing stop tier {tier} executed successfully for {position_id}: "
                        f"order_id={execution.order_id}, "
                        f"price={execution.exit_price:.4f}, "
                        f"profit={execution.profit_pct:.2%}, "
                        f"drawdown={trigger.actual_drawdown:.2%}"
                    )
                else:
                    self._failure_count += 1
                    logger.error(
                        f"Trailing stop tier {tier} execution failed for {position_id}: "
                        f"{execution.error_message}"
                    )

                # 触发回调
                self._notify_execution_callbacks(execution)

                return execution

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Trailing stop tier {tier} execution attempt {attempt + 1} failed for {position_id}: {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await self._sleep(self.config.retry_delay_ms / 1000)

        # 所有重试都失败
        self._failure_count += 1
        logger.error(
            f"Trailing stop tier {tier} execution failed after {self.config.max_retries} attempts for {position_id}"
        )

        execution = TrailingStopExecution(
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
        trigger: TrailingStopTrigger,
        attempt: int,
        expected_profit_pct: float,
        expected_profit_amount: float,
        **kwargs
    ) -> 'TrailingStopExecution':
        """
        下市价单平仓

        Args:
            position: 持仓数据
            trigger: 触发信号
            attempt: 当前重试次数
            expected_profit_pct: 预期盈利百分比
            expected_profit_amount: 预期盈利金额
            **kwargs: 额外参数

        Returns:
            TrailingStopExecution: 执行结果
        """
        position_id = position.position_id
        tier = trigger.tier
        exit_size = position.remaining_size  # 追踪止盈完全平仓

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
                client_order_id=f"trailing_stop_tier{tier}_{position_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
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

                return TrailingStopExecution(
                    position_id=position_id,
                    tier=tier,
                    success=True,
                    order_id=result.order_id,
                    exit_price=exit_price,
                    exit_size=exit_size,
                    profit_amount=profit_amount,
                    profit_pct=profit_pct,
                    slippage=slippage,
                    retry_count=attempt
                )
            else:
                return TrailingStopExecution(
                    position_id=position_id,
                    tier=tier,
                    success=False,
                    retry_count=attempt,
                    error_message=result.error_message or "Order creation failed"
                )

        except Exception as e:
            logger.error(f"Error placing market order for {position_id} tier {tier}: {e}")
            return TrailingStopExecution(
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

    def _notify_execution_callbacks(self, execution: TrailingStopExecution):
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

    def update_config(self, config: TrailingStopConfig):
        """更新配置"""
        self.config = config
        logger.info(f"Updated trailing stop config: tiers={len(config.tiers)}, enabled={config.enabled}")

    def reset_position(self, position_id: str) -> bool:
        """
        重置持仓的追踪止盈状态

        Args:
            position_id: 持仓 ID

        Returns:
            bool: 是否成功重置
        """
        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found for reset: {position_id}")
            return False

        # 重置最高价格
        position.highest_price = position.current_price

        # 重置档位
        position.current_tier = 0

        # 重置追踪止损价格
        position.trailing_stop_price = None

        logger.info(f"Reset trailing stop for position {position_id}")

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
                    "min_profit": t.min_profit,
                    "max_profit": t.max_profit,
                    "drawdown": t.drawdown,
                    "description": t.description
                }
                for t in self.config.tiers
            ]
        }


# 便捷函数

def create_default_trailing_stop_service(
    order_manager: Any,
    **kwargs
) -> TrailingStopService:
    """
    创建默认配置的追踪止盈服务

    Args:
        order_manager: OrderManager 实例
        **kwargs: 其他配置参数

    Returns:
        TrailingStopService: 追踪止盈服务
    """
    config = TrailingStopConfig(
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return TrailingStopService(order_manager=order_manager, config=config)


def create_custom_trailing_stop_service(
    order_manager: Any,
    tiers: List[TrailingTier],
    **kwargs
) -> TrailingStopService:
    """
    创建自定义档位的追踪止盈服务

    Args:
        order_manager: OrderManager 实例
        tiers: 自定义档位配置列表
        **kwargs: 其他配置参数

    Returns:
        TrailingStopService: 追踪止盈服务
    """
    config = TrailingStopConfig(
        tiers=tiers,
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return TrailingStopService(order_manager=order_manager, config=config)
