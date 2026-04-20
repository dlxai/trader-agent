"""
User Channel WebSocket Service

Polymarket User Channel WebSocket 服务

提供用户账户相关的实时数据：
- 订单状态更新
- 交易成交通知
- 持仓变化
- 账户余额变动
- 充值/提现状态

WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/user

参考文档: https://docs.polymarket.com/market-data/websocket/user-channel
"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any, Set
from enum import Enum
from dataclasses import dataclass, field
from urllib.parse import urlparse

import websocket

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================

class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"          # 待处理
    OPEN = "open"                # 已挂单
    FILLED = "filled"            # 完全成交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    CANCELLED = "cancelled"      # 已取消
    REJECTED = "rejected"        # 被拒绝
    EXPIRED = "expired"          # 已过期


class TradeSide(str, Enum):
    """交易方向"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """订单数据"""
    order_id: str
    market_id: str
    asset_id: str
    side: TradeSide
    price: float
    size: float
    filled_size: float = 0.0
    remaining_size: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: int = 0
    updated_at: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Trade:
    """交易数据"""
    trade_id: str
    order_id: str
    market_id: str
    asset_id: str
    side: TradeSide
    price: float
    size: float
    fee: float = 0.0
    timestamp: int = 0
    is_maker: bool = False


@dataclass
class Position:
    """持仓数据"""
    asset_id: str
    market_id: str
    token_id: str
    size: float
    average_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_updated: int = 0


@dataclass
class Balance:
    """余额数据"""
    asset: str  # USDC, etc.
    total: float
    available: float
    locked: float
    updated_at: int = 0


@dataclass
class Transfer:
    """充值/提现记录"""
    transfer_id: str
    type: str  # deposit, withdrawal
    asset: str
    amount: float
    status: str  # pending, completed, failed
    timestamp: int = 0
    tx_hash: Optional[str] = None


# =============================================================================
# User WebSocket 服务
# =============================================================================

class UserWebSocketService:
    """
    Polymarket User Channel WebSocket 服务

    提供用户账户的实时数据更新
    """

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy: Optional[str] = "http://127.0.0.1:7890",
        auto_reconnect: bool = True,
        max_reconnect_attempts: int = 5,
        ping_interval: int = 30,
    ):
        """
        初始化 User WebSocket 服务

        Args:
            api_key: API密钥（某些端点需要）
            proxy: 代理地址，默认 http://127.0.0.1:7890
            auto_reconnect: 是否自动重连
            max_reconnect_attempts: 最大重连次数
            ping_interval: Ping 间隔（秒）
        """
        self.api_key = api_key
        self.proxy = proxy
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.ping_interval = ping_interval

        # WebSocket 实例
        self._ws: Optional[websocket.WebSocketApp] = None
        self._connected = False
        self._reconnect_attempts = 0
        self._reconnecting = False

        # 线程和事件
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # 健康检查
        self._last_message_time: float = 0
        self._health_check_task: Optional[asyncio.Task] = None

        # 数据缓存
        self._orders: Dict[str, Order] = {}
        self._trades: Dict[str, Trade] = {}
        self._positions: Dict[str, Position] = {}
        self._balances: Dict[str, Balance] = {}

        # 事件处理器
        self._handlers: Dict[str, List[Callable]] = {
            "order_update": [],
            "trade": [],
            "position_update": [],
            "balance_update": [],
            "message": [],
            "error": [],
        }

        logger.info(f"[UserWebSocket] 初始化完成, proxy={proxy}")

    # ==========================================================================
    # 连接管理
    # ==========================================================================

    async def connect(self):
        """连接 WebSocket"""
        try:
            if self._connected:
                logger.info("[UserWebSocket] 已连接，跳过")
                return

            self._event_loop = asyncio.get_event_loop()

            logger.info(f"[UserWebSocket] 正在连接到 {self.WS_URL}...")

            # 构建 header（如果需要认证）
            header = {}
            if self.api_key:
                header["Authorization"] = f"Bearer {self.api_key}"

            self._ws = websocket.WebSocketApp(
                self.WS_URL,
                header=header,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_pong=self._on_pong,
            )

            self._stop_event.clear()
            self._ws_thread = threading.Thread(target=self._run_forever, daemon=True)
            self._ws_thread.start()

            # 等待连接建立
            for _ in range(100):
                if self._connected:
                    break
                await asyncio.sleep(0.1)
            else:
                raise ConnectionError("连接超时")

            self._last_message_time = time.time()
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info("[UserWebSocket] 已连接")

        except Exception as e:
            self._connected = False
            logger.error(f"[UserWebSocket] 连接失败: {e}")
            raise

    def _run_forever(self):
        """在单独线程中运行 WebSocket"""
        try:
            proxy_config = self._get_proxy_config()
            if proxy_config:
                self._ws.run_forever(
                    http_proxy_host=proxy_config["host"],
                    http_proxy_port=proxy_config["port"],
                    proxy_type=proxy_config["type"],
                    ping_interval=self.ping_interval,
                    ping_timeout=10,
                )
            else:
                self._ws.run_forever(
                    ping_interval=self.ping_interval, ping_timeout=10
                )
        except Exception as e:
            logger.error(f"[UserWebSocket] run_forever 错误: {e}")
            self._connected = False

    def _get_proxy_config(self) -> Optional[Dict]:
        """获取代理配置"""
        if not self.proxy:
            return None

        try:
            parsed = urlparse(self.proxy)
            return {
                "url": self.proxy,
                "host": parsed.hostname,
                "port": parsed.port or 7890,
                "type": parsed.scheme if parsed.scheme in ["http", "https", "socks5"] else "http",
            }
        except Exception as e:
            logger.warning(f"解析代理失败: {e}")
            return None

    async def disconnect(self):
        """断开连接"""
        logger.info("[UserWebSocket] 正在断开...")
        self._connected = False
        self._stop_event.set()

        if self._health_check_task:
            self._health_check_task.cancel()

        if self._ws:
            self._ws.close()
            self._ws = None

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)

        logger.info("[UserWebSocket] 已断开")

    # ==========================================================================
    # WebSocket 回调
    # ==========================================================================

    def _on_open(self, ws):
        """连接打开"""
        self._connected = True
        self._reconnect_attempts = 0
        logger.info("[UserWebSocket] 连接已建立")

    def _on_message(self, ws, message):
        """处理消息"""
        try:
            self._last_message_time = time.time()
            data = json.loads(message)

            # 调度异步处理
            if self._event_loop:
                asyncio.run_coroutine_threadsafe(self._handle_message(data), self._event_loop)

        except Exception as e:
            logger.error(f"[UserWebSocket] 处理消息失败: {e}")

    def _on_error(self, ws, error):
        """错误处理"""
        logger.error(f"[UserWebSocket] 错误: {error}")
        self._connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        logger.info(f"[UserWebSocket] 连接关闭: {close_status_code} - {close_msg}")
        self._connected = False

        if self.auto_reconnect and not self._stop_event.is_set():
            asyncio.create_task(self._reconnect())

    def _on_pong(self, ws, data):
        """收到 pong"""
        pass

    # ==========================================================================
    # 消息处理
    # ==========================================================================

    async def _handle_message(self, data: Dict[str, Any]):
        """处理消息"""
        msg_type = data.get("type")

        if msg_type == "order_update":
            await self._handle_order_update(data)
        elif msg_type == "trade":
            await self._handle_trade(data)
        elif msg_type == "position_update":
            await self._handle_position_update(data)
        elif msg_type == "balance_update":
            await self._handle_balance_update(data)

        # 触发通用消息处理器
        for handler in self._handlers.get("message", []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[UserWebSocket] message 处理器错误: {e}")

    async def _handle_order_update(self, data: Dict[str, Any]):
        """处理订单更新"""
        try:
            order = Order(
                order_id=data.get("order_id", ""),
                market_id=data.get("market_id", ""),
                asset_id=data.get("asset_id", ""),
                side=TradeSide(data.get("side", "buy")),
                price=float(data.get("price", 0)),
                size=float(data.get("size", 0)),
                filled_size=float(data.get("filled_size", 0)),
                remaining_size=float(data.get("remaining_size", 0)),
                status=OrderStatus(data.get("status", "pending")),
                created_at=data.get("created_at", 0),
                updated_at=data.get("updated_at", 0),
            )

            self._orders[order.order_id] = order

            # 触发处理器
            for handler in self._handlers.get("order_update", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(order)
                    else:
                        handler(order)
                except Exception as e:
                    logger.error(f"[UserWebSocket] order_update 处理器错误: {e}")

            logger.debug(f"[UserWebSocket] 订单更新: {order.order_id} - {order.status.value}")

        except Exception as e:
            logger.error(f"[UserWebSocket] 处理订单更新失败: {e}")

    async def _handle_trade(self, data: Dict[str, Any]):
        """处理成交"""
        try:
            trade = Trade(
                trade_id=data.get("trade_id", ""),
                order_id=data.get("order_id", ""),
                market_id=data.get("market_id", ""),
                asset_id=data.get("asset_id", ""),
                side=TradeSide(data.get("side", "buy")),
                price=float(data.get("price", 0)),
                size=float(data.get("size", 0)),
                fee=float(data.get("fee", 0)),
                timestamp=data.get("timestamp", 0),
                is_maker=data.get("is_maker", False),
            )

            self._trades[trade.trade_id] = trade

            # 触发处理器
            for handler in self._handlers.get("trade", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(trade)
                    else:
                        handler(trade)
                except Exception as e:
                    logger.error(f"[UserWebSocket] trade 处理器错误: {e}")

            logger.info(f"[UserWebSocket] 成交: {trade.trade_id} - {trade.side.value} {trade.size} @ {trade.price}")

        except Exception as e:
            logger.error(f"[UserWebSocket] 处理成交失败: {e}")

    async def _handle_position_update(self, data: Dict[str, Any]):
        """处理持仓更新"""
        try:
            position = Position(
                asset_id=data.get("asset_id", ""),
                market_id=data.get("market_id", ""),
                token_id=data.get("token_id", ""),
                size=float(data.get("size", 0)),
                average_price=float(data.get("average_price", 0)),
                unrealized_pnl=float(data.get("unrealized_pnl", 0)),
                realized_pnl=float(data.get("realized_pnl", 0)),
                last_updated=data.get("last_updated", 0),
            )

            key = f"{position.asset_id}_{position.token_id}"
            self._positions[key] = position

            # 触发处理器
            for handler in self._handlers.get("position_update", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(position)
                    else:
                        handler(position)
                except Exception as e:
                    logger.error(f"[UserWebSocket] position_update 处理器错误: {e}")

            logger.debug(f"[UserWebSocket] 持仓更新: {key} - size={position.size}")

        except Exception as e:
            logger.error(f"[UserWebSocket] 处理持仓更新失败: {e}")

    async def _handle_balance_update(self, data: Dict[str, Any]):
        """处理余额更新"""
        try:
            balance = Balance(
                asset=data.get("asset", "USDC"),
                total=float(data.get("total", 0)),
                available=float(data.get("available", 0)),
                locked=float(data.get("locked", 0)),
                updated_at=data.get("updated_at", 0),
            )

            self._balances[balance.asset] = balance

            # 触发处理器
            for handler in self._handlers.get("balance_update", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(balance)
                    else:
                        handler(balance)
                except Exception as e:
                    logger.error(f"[UserWebSocket] balance_update 处理器错误: {e}")

            logger.debug(f"[UserWebSocket] 余额更新: {balance.asset} - available={balance.available}")

        except Exception as e:
            logger.error(f"[UserWebSocket] 处理余额更新失败: {e}")

    # ==========================================================================
    # 事件处理器注册
    # ==========================================================================

    def on(self, event: str, handler: Callable):
        """
        注册事件处理器

        Args:
            event: 事件类型
                - order_update: 订单更新
                - trade: 成交
                - position_update: 持仓更新
                - balance_update: 余额更新
                - message: 所有消息
                - error: 错误
            handler: 处理函数
        """
        if event in self._handlers:
            self._handlers[event].append(handler)
            logger.debug(f"[UserWebSocket] 注册处理器: {event}")

    def off(self, event: str, handler: Optional[Callable] = None):
        """移除事件处理器"""
        if event not in self._handlers:
            return

        if handler is None:
            self._handlers[event].clear()
        else:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    # ==========================================================================
    # 数据获取
    # ==========================================================================

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._orders.get(order_id)

    def get_all_orders(self) -> Dict[str, Order]:
        """获取所有订单"""
        return self._orders.copy()

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """获取成交"""
        return self._trades.get(trade_id)

    def get_all_trades(self) -> Dict[str, Trade]:
        """获取所有成交"""
        return self._trades.copy()

    def get_position(self, asset_id: str, token_id: str) -> Optional[Position]:
        """获取持仓"""
        key = f"{asset_id}_{token_id}"
        return self._positions.get(key)

    def get_all_positions(self) -> Dict[str, Position]:
        """获取所有持仓"""
        return self._positions.copy()

    def get_balance(self, asset: str = "USDC") -> Optional[Balance]:
        """获取余额"""
        return self._balances.get(asset)

    def get_all_balances(self) -> Dict[str, Balance]:
        """获取所有余额"""
        return self._balances.copy()

    # ==========================================================================
    # 健康检查
    # ==========================================================================

    async def _health_check_loop(self):
        """健康检查循环"""
        while self._connected and not self._stop_event.is_set():
            try:
                await asyncio.sleep(30)

                if not self._connected:
                    break

                time_since_last = time.time() - self._last_message_time
                if time_since_last > 120:
                    logger.warning(f"[UserWebSocket] 静默 {time_since_last:.0f} 秒，重连...")
                    await self._reconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[UserWebSocket] 健康检查错误: {e}")

    async def _reconnect(self):
        """重新连接"""
        if self._reconnecting:
            return

        self._reconnecting = True
        try:
            await self.disconnect()
            await asyncio.sleep(2)
            await self.connect()
            logger.info("[UserWebSocket] 重连成功")
        except Exception as e:
            logger.error(f"[UserWebSocket] 重连失败: {e}")
        finally:
            self._reconnecting = False

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected


# =============================================================================
# 便捷函数
# =============================================================================

async def create_user_websocket(
    api_key: Optional[str] = None,
    proxy: str = "http://127.0.0.1:7890",
    auto_reconnect: bool = True,
) -> UserWebSocketService:
    """
    创建并连接 User WebSocket 服务

    Args:
        api_key: API密钥
        proxy: 代理地址
        auto_reconnect: 自动重连

    Returns:
        已连接的 UserWebSocketService 实例
    """
    service = UserWebSocketService(
        api_key=api_key,
        proxy=proxy,
        auto_reconnect=auto_reconnect,
    )
    await service.connect()
    return service


__all__ = [
    "UserWebSocketService",
    "OrderStatus",
    "TradeSide",
    "Order",
    "Trade",
    "Position",
    "Balance",
    "create_user_websocket",
]
