"""
Position Monitor - 双层持仓检查机制主类
Layer 1: 实时价格驱动检查
Layer 2: 定时链上持仓同步
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import logging

from ..config.settings import settings
from .realtime_checker import RealtimeChecker
from .periodic_sync import PeriodicSync
from .websocket_handler import WebSocketHandler


logger = logging.getLogger(__name__)


@dataclass
class Position:
    """持仓数据"""
    id: str
    token_id: str
    market_id: str
    entry_price: float
    current_price: float = 0.0
    highest_price: float = 0.0
    size: float = 0.0
    side: str = "BUY"  # BUY or SELL
    opened_at: datetime = field(default_factory=datetime.now)
    last_sync_at: datetime = field(default_factory=datetime.now)
    partial_exits_executed: List[int] = field(default_factory=list)
    trailing_stop_price: Optional[float] = None

    @property
    def profit_pct(self) -> float:
        """当前盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def from_high_pct(self) -> float:
        """从最高价回撤百分比"""
        if self.highest_price == 0:
            return 0.0
        return (self.current_price - self.highest_price) / self.highest_price

    def update_price(self, new_price: float):
        """更新价格并记录最高价"""
        self.current_price = new_price
        if new_price > self.highest_price:
            self.highest_price = new_price


@dataclass
class ExitSignal:
    """退出信号"""
    position_id: str
    action: str  # "exit", "partial_exit", "hold"
    reason: str  # "stop_loss", "take_profit", "trailing_stop", etc.
    exit_ratio: float = 1.0  # 1.0 = 全部退出
    target_price: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PositionMonitor:
    """
    双层持仓检查机制主类

    Layer 1: 实时价格驱动检查
    - 触发：每次价格更新（WebSocket）
    - 频率：毫秒级
    - 职责：硬止损/止盈、紧急退出

    Layer 2: 定时链上持仓同步
    - 触发：每 60 秒定时任务
    - 频率：分钟级
    - 职责：持仓漂移修正、强制退出检查
    """

    def __init__(self):
        self.config = settings.position_monitor

        # 持仓存储
        self._positions: Dict[str, Position] = {}

        # Layer 1: 实时检查器
        self.realtime_checker = RealtimeChecker(
            config=self.config.realtime_check,
            on_exit_signal=self._handle_exit_signal
        )

        # Layer 2: 定时同步器
        self.periodic_sync = PeriodicSync(
            config=self.config.periodic_sync,
            on_sync=self._handle_periodic_sync
        )

        # WebSocket 处理器
        self.websocket_handler = WebSocketHandler(
            config=self.config.websocket,
            on_price_update=self._handle_price_update
        )

        # 退出信号回调
        self._exit_callbacks: List[Callable[[ExitSignal], None]] = []

        self._running = False
        self._lock = asyncio.Lock()

    def register_exit_callback(self, callback: Callable[[ExitSignal], None]):
        """注册退出信号回调"""
        self._exit_callbacks.append(callback)

    async def start(self):
        """启动持仓监控"""
        if self._running:
            logger.warning("Position monitor is already running")
            return

        async with self._lock:
            self._running = True
            logger.info("Starting position monitor...")

            # 启动 Layer 2: 定时同步
            await self.periodic_sync.start()

            # 启动 WebSocket 连接
            await self.websocket_handler.start()

            logger.info("Position monitor started successfully")

    async def stop(self):
        """停止持仓监控"""
        if not self._running:
            return

        async with self._lock:
            self._running = False
            logger.info("Stopping position monitor...")

            # 停止 WebSocket
            await self.websocket_handler.stop()

            # 停止定时同步
            await self.periodic_sync.stop()

            logger.info("Position monitor stopped")

    def add_position(self, position: Position):
        """添加持仓"""
        self._positions[position.id] = position

        # 订阅该 token 的价格更新
        self.websocket_handler.subscribe_token(position.token_id)

        logger.info(f"Added position {position.id} for token {position.token_id}")

    def remove_position(self, position_id: str):
        """移除持仓"""
        if position_id in self._positions:
            position = self._positions[position_id]

            # 取消订阅
            self.websocket_handler.unsubscribe_token(position.token_id)

            del self._positions[position_id]
            logger.info(f"Removed position {position_id}")

    def get_position(self, position_id: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())

    def _handle_price_update(self, token_id: str, new_price: float):
        """
        处理价格更新 - Layer 1: 实时检查入口
        每次价格更新时触发
        """
        # 更新所有相关持仓的价格
        positions_to_check = []

        for position in self._positions.values():
            if position.token_id == token_id:
                position.update_price(new_price)
                positions_to_check.append(position)

        # 对每个持仓执行实时检查
        for position in positions_to_check:
            exit_signal = self.realtime_checker.check(position)
            if exit_signal:
                self._handle_exit_signal(exit_signal)

    def _handle_periodic_sync(self, sync_data: Dict):
        """
        处理定时同步 - Layer 2: 定时检查入口
        每 60 秒触发一次
        """
        # 同步链上持仓数据
        for position in self._positions.values():
            # 执行 Layer 2 检查
            exit_signal = self.periodic_sync.check_position(position, sync_data)
            if exit_signal:
                self._handle_exit_signal(exit_signal)

    def _handle_exit_signal(self, signal: ExitSignal):
        """处理退出信号"""
        logger.warning(
            f"Exit signal triggered: {signal.reason} "
            f"for position {signal.position_id} "
            f"(action: {signal.action}, ratio: {signal.exit_ratio})"
        )

        # 触发回调
        for callback in self._exit_callbacks:
            try:
                callback(signal)
            except Exception as e:
                logger.error(f"Error in exit callback: {e}")
