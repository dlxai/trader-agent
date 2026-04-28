"""
用户活动实时监控器
通过 Polymarket User Channel WebSocket 监控个人订单和持仓变化
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import websockets

logger = logging.getLogger(__name__)


class UserEventType(Enum):
    """用户事件类型"""
    ORDER_FILLED = "order_filled"           # 订单成交
    ORDER_PARTIALLY_FILLED = "order_partially_filled"  # 部分成交
    ORDER_CANCELLED = "order_cancelled"     # 订单取消
    ORDER_REJECTED = "order_rejected"       # 订单被拒绝
    POSITION_OPENED = "position_opened"     # 新开仓
    POSITION_CLOSED = "position_closed"     # 平仓
    POSITION_UPDATED = "position_updated"   # 持仓更新
    TRADE_SETTLED = "trade_settled"         # 交易结算


@dataclass
class OrderFill:
    """订单成交信息"""
    order_id: str
    token_id: str
    side: str  # "BUY" or "SELL"
    filled_size: float
    filled_price: float
    remaining_size: float
    timestamp: datetime
    fee: Optional[float] = None
    transaction_hash: Optional[str] = None


@dataclass
class PositionUpdate:
    """持仓更新"""
    position_id: str
    token_id: str
    market_id: str
    action: str  # "OPENED", "INCREASED", "DECREASED", "CLOSED"
    old_size: float
    new_size: float
    avg_entry_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class UserEvent:
    """用户事件"""
    event_type: UserEventType
    timestamp: datetime
    event_data: Dict[str, Any]
    raw_message: str = ""


class UserMonitor:
    """
    用户活动实时监控器

    职责：
    1. 通过 WebSocket 实时获取个人订单和持仓更新
    2. 同步本地持仓状态与链上实际状态
    3. 检测异常（订单被拒绝、持仓漂移等）
    4. 通知策略引擎处理事件

    WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/user
    需要 API Key 认证
    """

    def __init__(
        self,
        ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/user",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        on_order_fill: Optional[Callable[[OrderFill], None]] = None,
        on_position_update: Optional[Callable[[PositionUpdate], None]] = None,
        on_user_event: Optional[Callable[[UserEvent], None]] = None,
    ):
        self.ws_url = ws_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.on_order_fill = on_order_fill
        self.on_position_update = on_position_update
        self.on_user_event = on_user_event

        # WebSocket 连接
        self._ws = None
        self._running = False
        self._reconnect_interval = 5
        self._max_reconnect_attempts = 10

        # 状态追踪
        self._pending_orders: Dict[str, Dict] = {}  # 未完成的订单
        self._active_positions: Dict[str, Dict] = {}  # 当前持仓

        # 统计
        self._event_count = 0
        self._fill_count = 0
        self._last_event_time: Optional[datetime] = None

        logger.info(f"UserMonitor initialized (ws_url: {ws_url})")

    # ==================== WebSocket 连接管理 ====================

    async def start(self):
        """启动监控"""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info("Starting UserMonitor...")

        # 启动 WebSocket 连接循环
        asyncio.create_task(self._ws_connection_loop())

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping UserMonitor...")

        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

    async def _ws_connection_loop(self):
        """WebSocket 连接循环"""
        reconnect_attempts = 0

        while self._running:
            try:
                logger.debug(f"Connecting to {self.ws_url}...")

                # 建立 WebSocket 连接（需要认证）
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key
                if self.api_secret:
                    headers["X-API-Secret"] = self.api_secret

                self._ws = await websockets.connect(
                    self.ws_url,
                    extra_headers=headers if headers else None
                )

                reconnect_attempts = 0
                logger.info("WebSocket connected")

                # 处理消息循环
                await self._ws_message_loop()

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            # 重连逻辑
            if self._running:
                reconnect_attempts += 1
                if reconnect_attempts > self._max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached")
                    break

                wait_time = min(self._reconnect_interval * reconnect_attempts, 60)
                logger.info(f"Reconnecting in {wait_time}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(wait_time)

    async def _ws_message_loop(self):
        """处理 WebSocket 消息循环"""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                await self._handle_ws_message(message)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")

    async def _handle_ws_message(self, message: str):
        """处理单个 WebSocket 消息"""
        try:
            data = json.loads(message)
            if isinstance(data, list):
                return
            msg_type = data.get("type", "")

            if msg_type == "order_fill":
                await self._handle_order_fill(data)
            elif msg_type == "order_partial_fill":
                await self._handle_order_partial_fill(data)
            elif msg_type == "order_cancelled":
                await self._handle_order_cancelled(data)
            elif msg_type == "order_rejected":
                await self._handle_order_rejected(data)
            elif msg_type == "position_update":
                await self._handle_position_update(data)
            elif msg_type == "trade_settled":
                await self._handle_trade_settled(data)
            else:
                logger.debug(f"Unknown message type: {msg_type}")

            # 记录通用事件
            if msg_type:
                await self._handle_generic_event(msg_type, data, message)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    # ==================== 具体事件处理 ====================

    async def _handle_order_fill(self, data: Dict):
        """处理订单完全成交"""
        try:
            order_id = data.get("order_id", "")

            fill = OrderFill(
                order_id=order_id,
                token_id=data.get("token_id", ""),
                side=data.get("side", ""),
                filled_size=float(data.get("filled_size", 0)),
                filled_price=float(data.get("filled_price", 0)),
                remaining_size=0.0,
                timestamp=datetime.now(),
                fee=float(data.get("fee", 0)) if data.get("fee") else None,
                transaction_hash=data.get("transaction_hash")
            )

            # 从 pending 中移除
            if order_id in self._pending_orders:
                del self._pending_orders[order_id]

            self._fill_count += 1

            logger.info(
                f"Order filled: {order_id}, "
                f"{fill.side} {fill.filled_size} @ {fill.filled_price:.4f}"
            )

            # 触发回调
            if self.on_order_fill:
                await self.on_order_fill(fill)

        except Exception as e:
            logger.error(f"Error handling order fill: {e}")

    async def _handle_order_partial_fill(self, data: Dict):
        """处理订单部分成交"""
        try:
            order_id = data.get("order_id", "")

            fill = OrderFill(
                order_id=order_id,
                token_id=data.get("token_id", ""),
                side=data.get("side", ""),
                filled_size=float(data.get("filled_size", 0)),
                filled_price=float(data.get("filled_price", 0)),
                remaining_size=float(data.get("remaining_size", 0)),
                timestamp=datetime.now(),
                fee=float(data.get("fee", 0)) if data.get("fee") else None,
                transaction_hash=data.get("transaction_hash")
            )

            # 更新 pending 订单
            self._pending_orders[order_id] = {
                "filled_size": fill.filled_size,
                "remaining_size": fill.remaining_size,
                "avg_price": fill.filled_price
            }

            logger.info(
                f"Order partially filled: {order_id}, "
                f"{fill.side} {fill.filled_size} @ {fill.filled_price:.4f}, "
                f"remaining: {fill.remaining_size}"
            )

            # 触发回调
            if self.on_order_fill:
                await self.on_order_fill(fill)

        except Exception as e:
            logger.error(f"Error handling order partial fill: {e}")

    async def _handle_order_cancelled(self, data: Dict):
        """处理订单取消"""
        try:
            order_id = data.get("order_id", "")

            if order_id in self._pending_orders:
                del self._pending_orders[order_id]

            logger.info(f"Order cancelled: {order_id}")

            # 可以触发回调通知策略引擎

        except Exception as e:
            logger.error(f"Error handling order cancelled: {e}")

    async def _handle_order_rejected(self, data: Dict):
        """处理订单被拒绝"""
        try:
            order_id = data.get("order_id", "")
            reason = data.get("reason", "Unknown")

            if order_id in self._pending_orders:
                del self._pending_orders[order_id]

            logger.warning(f"Order rejected: {order_id}, reason: {reason}")

            # 触发警报通知策略引擎

        except Exception as e:
            logger.error(f"Error handling order rejected: {e}")

    async def _handle_position_update(self, data: Dict):
        """处理持仓更新"""
        try:
            position_id = data.get("position_id", "")
            token_id = data.get("token_id", "")
            action = data.get("action", "")

            update = PositionUpdate(
                position_id=position_id,
                token_id=token_id,
                market_id=data.get("market_id", ""),
                action=action,
                old_size=float(data.get("old_size", 0)),
                new_size=float(data.get("new_size", 0)),
                avg_entry_price=float(data.get("avg_entry_price", 0)) if data.get("avg_entry_price") else None,
                realized_pnl=float(data.get("realized_pnl", 0)) if data.get("realized_pnl") else None,
                timestamp=datetime.now()
            )

            # 更新本地持仓追踪
            if action == "CLOSED":
                if position_id in self._active_positions:
                    del self._active_positions[position_id]
            else:
                self._active_positions[position_id] = {
                    "token_id": token_id,
                    "size": update.new_size,
                    "avg_price": update.avg_entry_price
                }

            logger.info(
                f"Position updated: {position_id}, action={action}, "
                f"size {update.old_size:.4f} -> {update.new_size:.4f}"
            )

            # 触发回调
            if self.on_position_update:
                await self.on_position_update(update)

        except Exception as e:
            logger.error(f"Error handling position update: {e}")

    async def _handle_trade_settled(self, data: Dict):
        """处理交易结算"""
        try:
            trade_id = data.get("trade_id", "")
            logger.info(f"Trade settled: {trade_id}")

            # 可以在这里更新持仓成本基础

        except Exception as e:
            logger.error(f"Error handling trade settled: {e}")

    async def _handle_generic_event(self, event_type: str, data: Dict, raw_message: str):
        """处理通用事件"""
        try:
            user_event_type = UserEventType(event_type)
        except ValueError:
            user_event_type = UserEventType.POSITION_UPDATED  # 默认

        event = UserEvent(
            event_type=user_event_type,
            timestamp=datetime.now(),
            event_data=data,
            raw_message=raw_message
        )

        self._event_count += 1
        self._last_event_time = datetime.now()

        if self.on_user_event:
            await self.on_user_event(event)

    # ==================== 公共接口 ====================

    def get_pending_orders(self) -> Dict[str, Dict]:
        """获取未完成的订单列表"""
        return self._pending_orders.copy()

    def get_active_positions(self) -> Dict[str, Dict]:
        """获取当前持仓列表"""
        return self._active_positions.copy()

    def is_order_pending(self, order_id: str) -> bool:
        """检查订单是否未完成"""
        return order_id in self._pending_orders

    def get_stats(self) -> Dict:
        """获取监控统计"""
        return {
            "is_running": self._running,
            "ws_connected": self._ws is not None and self._ws.open,
            "pending_orders": len(self._pending_orders),
            "active_positions": len(self._active_positions),
            "event_count": self._event_count,
            "fill_count": self._fill_count,
            "last_event_time": self._last_event_time.isoformat() if self._last_event_time else None,
        }
