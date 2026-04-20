"""
固定止损服务 (Fixed Stop Loss Service)

基于固定金额或百分比的止损逻辑，支持 YES/NO 代币的双向止损。
当价格触及止损线时触发平仓，市价单完全平仓。
"""

import logging
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from abc import ABC, abstractmethod

from ..config.settings import settings

logger = logging.getLogger(__name__)


class TokenType(Enum):
    """代币类型"""
    YES = "yes"
    NO = "no"


class StopLossType(Enum):
    """止损类型"""
    FIXED_AMOUNT = "fixed_amount"
    FIXED_PERCENTAGE = "fixed_percentage"


@dataclass
class StopLossConfig:
    """止损配置"""
    enabled: bool = True
    type: StopLossType = StopLossType.FIXED_AMOUNT
    amount: float = 0.05  # 固定金额止损（如 $0.05）
    percentage: float = 0.10  # 固定百分比止损（如 10%）
    slippage_tolerance: float = 0.02  # 滑价容忍度 2%
    max_retries: int = 3  # 最大重试次数
    retry_delay_ms: int = 1000  # 重试延迟（毫秒）


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
    side: str = "LONG"  # LONG or SHORT
    opened_at: datetime = field(default_factory=datetime.now)
    stop_loss_price: Optional[float] = None  # 计算的止损价格
    is_stop_loss_set: bool = False

    def update_price(self, new_price: float):
        """更新当前价格"""
        self.current_price = new_price

    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏（以代币计价）"""
        if self.token_type == TokenType.YES:
            return (self.current_price - self.entry_price) * self.size
        else:  # NO token
            return (self.entry_price - self.current_price) * self.size

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
class StopLossTrigger:
    """止损触发信号"""
    position_id: str
    token_id: str
    trigger_type: str  # "fixed_amount" or "fixed_percentage"
    entry_price: float
    stop_loss_price: float
    current_price: float
    token_type: TokenType
    should_exit: bool = True
    exit_ratio: float = 1.0  # 完全平仓
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "token_id": self.token_id,
            "trigger_type": self.trigger_type,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "current_price": self.current_price,
            "token_type": self.token_type.value,
            "should_exit": self.should_exit,
            "exit_ratio": self.exit_ratio,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class StopLossExecution:
    """止损执行结果"""
    position_id: str
    success: bool
    order_id: Optional[str] = None
    exit_price: Optional[float] = None
    exit_size: float = 0.0
    slippage: float = 0.0
    retry_count: int = 0
    error_message: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position_id": self.position_id,
            "success": self.success,
            "order_id": self.order_id,
            "exit_price": self.exit_price,
            "exit_size": self.exit_size,
            "slippage": self.slippage,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "executed_at": self.executed_at.isoformat(),
        }


class StopLossStrategy(ABC):
    """止损策略抽象基类"""

    @abstractmethod
    def calculate_stop_loss_price(
        self,
        entry_price: float,
        token_type: TokenType,
        config: StopLossConfig
    ) -> float:
        """计算止损价格"""
        pass

    @abstractmethod
    def check_trigger(
        self,
        position: Position,
        config: StopLossConfig
    ) -> Optional[StopLossTrigger]:
        """检查是否触发止损"""
        pass


class FixedAmountStopLoss(StopLossStrategy):
    """固定金额止损策略"""

    def calculate_stop_loss_price(
        self,
        entry_price: float,
        token_type: TokenType,
        config: StopLossConfig
    ) -> float:
        """
        计算固定金额止损价格

        Args:
            entry_price: 入场价格
            token_type: 代币类型 (YES/NO)
            config: 止损配置

        Returns:
            止损价格
        """
        stop_amount = config.amount

        if token_type == TokenType.YES:
            # Long YES: 价格下跌时止损
            # 当市场价格 <= entry_price - stop_loss_amount 时触发
            stop_price = max(0.0, entry_price - stop_amount)
        else:  # NO token
            # Long NO: 价格上涨时止损
            # 当市场价格 >= entry_price + stop_loss_amount 时触发
            stop_price = min(1.0, entry_price + stop_amount)

        return round(stop_price, 4)

    def check_trigger(
        self,
        position: Position,
        config: StopLossConfig
    ) -> Optional[StopLossTrigger]:
        """
        检查固定金额止损是否触发

        Args:
            position: 持仓数据
            config: 止损配置

        Returns:
            StopLossTrigger 如果触发，否则 None
        """
        if not position.is_stop_loss_set or position.stop_loss_price is None:
            return None

        current_price = position.current_price
        stop_price = position.stop_loss_price
        token_type = position.token_type

        triggered = False

        if token_type == TokenType.YES:
            # Long YES: 当前价格 <= 止损价格时触发
            triggered = current_price <= stop_price
        else:  # NO token
            # Long NO: 当前价格 >= 止损价格时触发
            triggered = current_price >= stop_price

        if triggered:
            return StopLossTrigger(
                position_id=position.position_id,
                token_id=position.token_id,
                trigger_type="fixed_amount",
                entry_price=position.entry_price,
                stop_loss_price=stop_price,
                current_price=current_price,
                token_type=token_type,
                should_exit=True,
                exit_ratio=1.0,
                reason=f"Fixed amount stop loss triggered: {token_type.value} price "
                       f"{current_price:.4f} crossed stop level {stop_price:.4f}"
            )

        return None


class FixedPercentageStopLoss(StopLossStrategy):
    """固定百分比止损策略"""

    def calculate_stop_loss_price(
        self,
        entry_price: float,
        token_type: TokenType,
        config: StopLossConfig
    ) -> float:
        """
        计算固定百分比止损价格

        Args:
            entry_price: 入场价格
            token_type: 代币类型 (YES/NO)
            config: 止损配置

        Returns:
            止损价格
        """
        percentage = config.percentage

        if token_type == TokenType.YES:
            # Long YES: 价格下跌时止损
            # 当市场价格 <= entry_price * (1 - percentage) 时触发
            stop_price = max(0.0, entry_price * (1 - percentage))
        else:  # NO token
            # Long NO: 价格上涨时止损
            # 当市场价格 >= entry_price * (1 + percentage) 时触发
            stop_price = min(1.0, entry_price * (1 + percentage))

        return round(stop_price, 4)

    def check_trigger(
        self,
        position: Position,
        config: StopLossConfig
    ) -> Optional[StopLossTrigger]:
        """
        检查固定百分比止损是否触发

        Args:
            position: 持仓数据
            config: 止损配置

        Returns:
            StopLossTrigger 如果触发，否则 None
        """
        if not position.is_stop_loss_set or position.stop_loss_price is None:
            return None

        current_price = position.current_price
        stop_price = position.stop_loss_price
        token_type = position.token_type

        triggered = False

        if token_type == TokenType.YES:
            # Long YES: 当前价格 <= 止损价格时触发
            triggered = current_price <= stop_price
        else:  # NO token
            # Long NO: 当前价格 >= 止损价格时触发
            triggered = current_price >= stop_price

        if triggered:
            # 计算实际亏损百分比
            if token_type == TokenType.YES:
                actual_loss_pct = (entry_price - current_price) / entry_price
            else:
                actual_loss_pct = (current_price - entry_price) / (1 - entry_price)

            return StopLossTrigger(
                position_id=position.position_id,
                token_id=position.token_id,
                trigger_type="fixed_percentage",
                entry_price=position.entry_price,
                stop_loss_price=stop_price,
                current_price=current_price,
                token_type=token_type,
                should_exit=True,
                exit_ratio=1.0,
                reason=f"Fixed percentage stop loss triggered: {token_type.value} price "
                       f"{current_price:.4f} crossed stop level {stop_price:.4f} "
                       f"(actual loss: {actual_loss_pct:.2%})"
            )

        return None


class FixedStopLossExecutor:
    """固定止损执行器"""

    def __init__(
        self,
        order_manager: Any,  # OrderManager instance
        config: Optional[StopLossConfig] = None
    ):
        """
        初始化固定止损执行器

        Args:
            order_manager: OrderManager 实例
            config: 止损配置
        """
        self.order_manager = order_manager
        self.config = config or StopLossConfig()

        # 策略映射
        self._strategies: Dict[StopLossType, StopLossStrategy] = {
            StopLossType.FIXED_AMOUNT: FixedAmountStopLoss(),
            StopLossType.FIXED_PERCENTAGE: FixedPercentageStopLoss(),
        }

        # 持仓止损状态跟踪
        self._positions: Dict[str, Position] = {}

        # 执行回调
        self._execution_callbacks: List[Callable[[StopLossExecution], None]] = []

        # 统计
        self._trigger_count = 0
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0

        logger.info(
            f"Fixed stop loss executor initialized: "
            f"type={self.config.type.value}, "
            f"enabled={self.config.enabled}"
        )

    def register_execution_callback(self, callback: Callable[[StopLossExecution], None]):
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
        添加持仓并设置止损

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
            side=side
        )

        # 计算并设置止损价格
        self._set_stop_loss_price(position)

        # 保存持仓
        self._positions[position_id] = position

        logger.info(
            f"Added position {position_id} with stop loss: "
            f"entry={entry_price:.4f}, stop={position.stop_loss_price:.4f}, "
            f"type={token_type.value}"
        )

        return position

    def _set_stop_loss_price(self, position: Position):
        """设置持仓的止损价格"""
        strategy = self._strategies.get(self.config.type)
        if not strategy:
            logger.error(f"Unknown stop loss strategy: {self.config.type}")
            return

        stop_price = strategy.calculate_stop_loss_price(
            entry_price=position.entry_price,
            token_type=position.token_type,
            config=self.config
        )

        position.stop_loss_price = stop_price
        position.is_stop_loss_set = True

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

    def update_price(self, position_id: str, current_price: float) -> Optional[StopLossTrigger]:
        """
        更新价格并检查是否触发止损

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            StopLossTrigger 如果触发止损，否则 None
        """
        if not self.config.enabled:
            return None

        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return None

        # 更新价格
        position.update_price(current_price)

        # 检查是否触发止损
        strategy = self._strategies.get(self.config.type)
        if not strategy:
            logger.error(f"Unknown stop loss strategy: {self.config.type}")
            return None

        trigger = strategy.check_trigger(position, self.config)

        if trigger:
            self._trigger_count += 1
            logger.warning(
                f"Stop loss triggered for {position_id}: "
                f"type={trigger.trigger_type}, "
                f"price={current_price:.4f}, "
                f"stop={trigger.stop_loss_price:.4f}"
            )

        return trigger

    async def execute_stop_loss(
        self,
        trigger: StopLossTrigger,
        **kwargs
    ) -> StopLossExecution:
        """
        执行止损平仓

        Args:
            trigger: 止损触发信号
            **kwargs: 额外参数传递给 order_manager

        Returns:
            StopLossExecution: 执行结果
        """
        self._execution_count += 1
        position_id = trigger.position_id

        # 获取持仓
        position = self._positions.get(position_id)
        if not position:
            logger.error(f"Position not found for execution: {position_id}")
            self._failure_count += 1
            return StopLossExecution(
                position_id=position_id,
                success=False,
                error_message=f"Position not found: {position_id}"
            )

        # 重试逻辑
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                # 调用 OrderManager 创建市价单平仓
                execution = await self._place_market_order(
                    position=position,
                    trigger=trigger,
                    attempt=attempt,
                    **kwargs
                )

                if execution.success:
                    self._success_count += 1
                    # 移除持仓
                    self.remove_position(position_id)
                    logger.info(
                        f"Stop loss executed successfully for {position_id}: "
                        f"order_id={execution.order_id}, "
                        f"price={execution.exit_price:.4f}"
                    )
                else:
                    self._failure_count += 1
                    logger.error(
                        f"Stop loss execution failed for {position_id}: "
                        f"{execution.error_message}"
                    )

                # 触发回调
                self._notify_execution_callbacks(execution)

                return execution

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Stop loss execution attempt {attempt + 1} failed for {position_id}: {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await self._sleep(self.config.retry_delay_ms / 1000)

        # 所有重试都失败
        self._failure_count += 1
        logger.error(
            f"Stop loss execution failed after {self.config.max_retries} attempts for {position_id}"
        )

        execution = StopLossExecution(
            position_id=position_id,
            success=False,
            retry_count=self.config.max_retries,
            error_message=last_error or f"Failed after {self.config.max_retries} attempts"
        )

        self._notify_execution_callbacks(execution)
        return execution

    async def _place_market_order(
        self,
        position: Position,
        trigger: StopLossTrigger,
        attempt: int,
        **kwargs
    ) -> StopLossExecution:
        """
        下市价单平仓

        Args:
            position: 持仓数据
            trigger: 触发信号
            attempt: 当前重试次数
            **kwargs: 额外参数

        Returns:
            StopLossExecution: 执行结果
        """
        position_id = position.position_id

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
                size=position.size,
                price=None,  # 市价单
                order_type=OrderType.MARKET,
                client_order_id=f"stop_loss_{position_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )

            # 调用 OrderManager 创建订单
            # 注意: 这里假设 order_manager 有 create_order 方法
            # 实际使用时需要确保传入的 order_manager 是正确的实例
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

                # 检查滑价是否超过容忍度
                if slippage > self.config.slippage_tolerance:
                    logger.warning(
                        f"High slippage detected for {position_id}: "
                        f"{slippage:.2%} > {self.config.slippage_tolerance:.2%}"
                    )

                return StopLossExecution(
                    position_id=position_id,
                    success=True,
                    order_id=result.order_id,
                    exit_price=exit_price,
                    exit_size=position.size,
                    slippage=slippage,
                    retry_count=attempt
                )
            else:
                return StopLossExecution(
                    position_id=position_id,
                    success=False,
                    retry_count=attempt,
                    error_message=result.error_message or "Order creation failed"
                )

        except Exception as e:
            logger.error(f"Error placing market order for {position_id}: {e}")
            return StopLossExecution(
                position_id=position_id,
                success=False,
                retry_count=attempt,
                error_message=str(e)
            )

    def _sync_create_order(self, order_params) -> Any:
        """同步创建订单（用于在线程池中执行）"""
        # 这里需要根据实际的 OrderManager 接口实现
        # 如果 OrderManager 是异步的，这个方法不会被使用
        raise NotImplementedError(
            "Synchronous order creation not supported. "
            "Please use an async OrderManager."
        )

    async def _sleep(self, seconds: float):
        """异步睡眠"""
        import asyncio
        await asyncio.sleep(seconds)

    def _notify_execution_callbacks(self, execution: StopLossExecution):
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

    def update_stop_loss_config(self, config: StopLossConfig):
        """更新止损配置"""
        self.config = config
        logger.info(f"Updated stop loss config: type={config.type.value}, enabled={config.enabled}")

    def reset_position_stop_loss(self, position_id: str) -> bool:
        """
        重置持仓的止损设置

        Args:
            position_id: 持仓 ID

        Returns:
            bool: 是否成功重置
        """
        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found for reset: {position_id}")
            return False

        # 重新计算止损价格
        self._set_stop_loss_price(position)

        logger.info(
            f"Reset stop loss for {position_id}: "
            f"entry={position.entry_price:.4f}, "
            f"new_stop={position.stop_loss_price:.4f}"
        )

        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "enabled": self.config.enabled,
            "type": self.config.type.value,
            "amount": self.config.amount,
            "percentage": self.config.percentage,
            "positions_count": len(self._positions),
            "trigger_count": self._trigger_count,
            "execution_count": self._execution_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": self._success_count / self._execution_count if self._execution_count > 0 else 0.0,
        }


# 便捷函数

def create_fixed_amount_stop_loss(
    order_manager: Any,
    amount: float = 0.05,
    **kwargs
) -> FixedStopLossExecutor:
    """
    创建固定金额止损执行器

    Args:
        order_manager: OrderManager 实例
        amount: 止损金额（如 0.05 表示 $0.05）
        **kwargs: 其他配置参数

    Returns:
        FixedStopLossExecutor: 止损执行器
    """
    config = StopLossConfig(
        type=StopLossType.FIXED_AMOUNT,
        amount=amount,
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return FixedStopLossExecutor(order_manager=order_manager, config=config)


def create_fixed_percentage_stop_loss(
    order_manager: Any,
    percentage: float = 0.10,
    **kwargs
) -> FixedStopLossExecutor:
    """
    创建固定百分比止损执行器

    Args:
        order_manager: OrderManager 实例
        percentage: 止损百分比（如 0.10 表示 10%）
        **kwargs: 其他配置参数

    Returns:
        FixedStopLossExecutor: 止损执行器
    """
    config = StopLossConfig(
        type=StopLossType.FIXED_PERCENTAGE,
        percentage=percentage,
        **{k: v for k, v in kwargs.items() if k in [
            'enabled', 'slippage_tolerance', 'max_retries', 'retry_delay_ms'
        ]}
    )
    return FixedStopLossExecutor(order_manager=order_manager, config=config)
