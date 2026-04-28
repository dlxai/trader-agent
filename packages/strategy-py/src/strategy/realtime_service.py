"""
Realtime Service

WebSocket 实时数据服务，提供：
- 市场订单簿实时推送
- 交易活动监控
- 价格更新
- 自动重连
- 事件驱动
- 代理支持

注意：此版本已移除对 polymarket_sdk 的依赖，使用 Python 内置机制实现
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

import websocket  # websocket-client 库

logger = logging.getLogger(__name__)


# =============================================================================
# 内置事件系统 (替代 polymarket_sdk.core.events)
# =============================================================================

class EventEmitter:
    """简单的事件发射器，替代 polymarket_sdk 的 EventEmitter"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, event: str, callback: Callable):
        """注册事件监听器"""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event: str, *args, **kwargs):
        """触发事件"""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in event listener for {event}: {e}")


# =============================================================================
# 错误处理 (替代 polymarket_sdk.core.errors)
# =============================================================================

class ErrorCode(Enum):
    """错误代码枚举"""
    NETWORK_ERROR = "network_error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    UNKNOWN_ERROR = "unknown_error"


class PolymarketError(Exception):
    """Polymarket 自定义异常"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        retryable: bool = False,
        details: Optional[Dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.details = details or {}


# =============================================================================
# 代理助手 (替代 ..utils.proxy_helper)
# =============================================================================

@dataclass
class ProxyConfig:
    """代理配置"""
    url: str
    host: str
    port: int
    type: str  # http, https, socks5
    username: Optional[str] = None
    password: Optional[str] = None


class ProxyHelper:
    """代理配置助手"""

    @staticmethod
    def get_proxy_config(proxy_url: Optional[str] = None) -> Optional[Dict]:
        """
        获取代理配置

        Args:
            proxy_url: 代理地址，例如 http://127.0.0.1:7890
            如果不提供，尝试从环境变量 HTTP_PROXY/HTTPS_PROXY 读取

        Returns:
            代理配置字典或 None
        """
        # 优先使用传入的代理地址
        url = proxy_url

        # 如果没有传入，尝试环境变量
        if not url:
            import os
            url = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')

        if not url:
            return None

        try:
            parsed = urlparse(url)

            # 确定代理类型
            proxy_type = "http"
            if parsed.scheme == "https":
                proxy_type = "https"
            elif parsed.scheme == "socks5":
                proxy_type = "socks5"

            return {
                "url": url,
                "host": parsed.hostname,
                "port": parsed.port or (8080 if proxy_type == "http" else 7890),
                "type": proxy_type,
                "username": parsed.username,
                "password": parsed.password,
            }
        except Exception as e:
            logger.warning(f"Failed to parse proxy URL {url}: {e}")
            return None


# =============================================================================
# WebSocket 枚举类型
# =============================================================================

class WebSocketTopic(str, Enum):
    """WebSocket 主题"""
    CLOB_MARKET = "clob_market"
    ACTIVITY = "activity"
    CRYPTO_PRICES = "crypto_prices"
    USER = "user"


class MessageType(str, Enum):
    """消息类型"""
    AGG_ORDERBOOK = "agg_orderbook"
    LAST_TRADE_PRICE = "last_trade_price"
    TRADE = "trade"
    BOOK = "book"
    USER_TRADE = "user_trade"
    USER_ORDER = "user_order"


# =============================================================================
# RealtimeService 主类
# =============================================================================

class RealtimeService(EventEmitter):
    """
    WebSocket 实时服务

    提供实时数据推送：
    - 订单簿更新
    - 交易活动
    - 价格变化
    - 用户订单/交易

    特点：
    - 自动重连
    - 代理支持 (默认 http://127.0.0.1:7890)
    - 应用层健康监控
    """

    # WebSocket 端点配置
    WS_URL_LIVE_DATA = "wss://ws-live-data.polymarket.com"
    WS_URL_CLOB = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        url: Optional[str] = None,
        auto_reconnect: bool = True,
        ping_interval: int = 30,
        max_reconnect_attempts: int = 5,
        proxy: Optional[str] = "http://127.0.0.1:7890",  # 默认使用本地代理
    ):
        """
        初始化实时服务

        Args:
            url: WebSocket URL（默认使用Live Data）
            auto_reconnect: 是否自动重连
            ping_interval: Ping 间隔（秒）
            max_reconnect_attempts: 最大重连次数
            proxy: 代理地址，默认 http://127.0.0.1:7890
        """
        super().__init__()
        self.WS_URL = url or self.WS_URL_LIVE_DATA
        self.auto_reconnect = auto_reconnect
        self.ping_interval = ping_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        # 代理配置（WSS 使用 HTTPS 代理）
        self.proxy_config = ProxyHelper.get_proxy_config(proxy)

        self._ws: Optional[websocket.WebSocketApp] = None
        self._connected = False
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._price_cache: Dict[str, float] = {}
        self._reconnect_attempts = 0
        self._reconnecting = False
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ping_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # 应用层健康监控
        self._last_message_time: float = 0
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval: int = 60
        self._health_check_timeout: int = 180

        logger.info(f"[RealtimeService] 初始化完成, proxy={proxy}")

    # ========================================================================
    # 连接管理
    # ========================================================================

    async def connect(self):
        """连接 WebSocket"""
        try:
            if self._connected:
                logger.info("[WebSocket] 已连接，跳过重复连接请求")
                return

            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()

            self._event_loop = asyncio.get_event_loop()

            logger.info(f"[WebSocket] 正在连接到 {self.WS_URL}...")
            if self.proxy_config:
                logger.info(f"[WebSocket] 使用代理: {self.proxy_config['url']}")

            self._ws = websocket.WebSocketApp(
                self.WS_URL,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_pong=self._on_pong,
            )

            self._stop_event.clear()
            self._ws_thread = threading.Thread(target=self._run_forever, daemon=True)
            self._ws_thread.start()

            for _ in range(100):
                if self._connected:
                    break
                await asyncio.sleep(0.1)
            else:
                raise PolymarketError("WebSocket 连接超时", ErrorCode.NETWORK_ERROR)

            self._last_message_time = time.time()
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info(f"[WebSocket] 已连接到 {self.WS_URL}")
            self.emit("connected")

        except Exception as e:
            self._connected = False
            error_msg = f"WebSocket 连接失败: {type(e).__name__}: {str(e)}"
            logger.error(f"[WebSocket] {error_msg}")
            self.emit("error", PolymarketError(error_msg, ErrorCode.NETWORK_ERROR, retryable=True))
            raise

    def _run_forever(self):
        """在单独线程中运行 WebSocket"""
        try:
            if self.proxy_config:
                self._ws.run_forever(
                    http_proxy_host=self.proxy_config["host"],
                    http_proxy_port=self.proxy_config["port"],
                    proxy_type=self.proxy_config["type"],
                    ping_interval=self.ping_interval,
                    ping_timeout=10,
                )
            else:
                self._ws.run_forever(
                    ping_interval=self.ping_interval, ping_timeout=10
                )
        except Exception as e:
            logger.error(f"[WebSocket] run_forever 错误: {e}")
            self._connected = False

    async def disconnect(self):
        """断开连接"""
        logger.info("[WebSocket] 正在断开连接...")
        self._connected = False
        self._stop_event.set()

        if self._health_check_task and not self._health_check_task.done():
            current_task = asyncio.current_task()
            if self._health_check_task != current_task:
                self._health_check_task.cancel()

        if self._ws:
            self._ws.close()
            self._ws = None

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)

        self.emit("disconnected")
        logger.info("[WebSocket] 已断开连接")

    async def _reconnect(self):
        """自动重连"""
        if not self.auto_reconnect:
            return

        if self._reconnecting:
            logger.info("[WebSocket] 已有重连任务在运行，跳过")
            return

        self._reconnecting = True
        try:
            while self._reconnect_attempts < self.max_reconnect_attempts:
                self._reconnect_attempts += 1
                delay = min(2**self._reconnect_attempts, 60)

                logger.info(
                    f"[WebSocket] 尝试重连 ({self._reconnect_attempts}/{self.max_reconnect_attempts})，等待 {delay} 秒..."
                )
                await asyncio.sleep(delay)

                try:
                    await self.connect()
                    return
                except Exception as e:
                    logger.warning(f"[WebSocket] 重连失败: {str(e)}")

            logger.warning("[WebSocket] 达到最大重连次数，停止重连")
            self.emit("max_reconnect_reached")
        finally:
            self._reconnecting = False

    # ========================================================================
    # WebSocket 回调
    # ========================================================================

    def _on_open(self, ws):
        """WebSocket 打开"""
        self._connected = True
        self._reconnect_attempts = 0
        logger.info("[WebSocket] 连接已建立")

        if self._subscriptions and self._event_loop:
            self._schedule_async_handler(self._resubscribe_all)

    def _on_message(self, ws, message):
        """处理 WebSocket 消息"""
        try:
            self._last_message_time = time.time()

            if not message or not message.strip():
                return

            data = json.loads(message)

            if not hasattr(self, "_message_count"):
                self._message_count = 0
            self._message_count += 1
            if self._message_count % 100 == 1:
                if isinstance(data, dict):
                    keys = list(data.keys())
                else:
                    keys = f"list[{len(data)}]"
                logger.debug(f"WebSocket message #{self._message_count}: {keys}")

            self._schedule_async_handler(self._handle_message, data)
        except json.JSONDecodeError as e:
            if message and message.strip():
                logger.error(f"[WebSocket] JSON 解析失败: {str(e)} | message: {message[:100]}")
        except Exception as e:
            logger.error(f"[WebSocket] 处理消息失败: {str(e)}")

    def _on_error(self, ws, error):
        """WebSocket 错误"""
        logger.error(f"[WebSocket] 错误: {error}")
        self._connected = False
        self.emit("error", error)

        if self.auto_reconnect:
            self._schedule_async_handler(self._reconnect)

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 关闭"""
        logger.info(f"[WebSocket] 连接已关闭: code={close_status_code}, msg={close_msg}")
        self._connected = False
        self.emit("disconnected")

        if self.auto_reconnect and not self._stop_event.is_set():
            self._schedule_async_handler(self._reconnect)

    def _on_pong(self, ws, data):
        """收到 pong"""
        self.emit("pong")

    def _schedule_async_handler(self, coro_func, *args):
        """在事件循环中调度异步处理函数"""
        if self._event_loop and not self._event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro_func(*args), self._event_loop)

    # ========================================================================
    # 消息处理
    # ========================================================================

    async def _handle_message(self, data: Dict[str, Any]):
        """处理 WebSocket 消息"""
        topic = data.get("topic")
        msg_type = data.get("type")

        if topic and msg_type:
            await self._handle_live_data_message(data)
            return

        if data.get("type") == "pong":
            self.emit("pong")
            return

        if data.get("type") == "subscribed":
            self.emit("subscribed", data)
            return

        event_type = data.get("event_type")
        if not event_type:
            return

        if event_type == "book":
            await self._handle_orderbook(data)
        elif event_type == "trade":
            await self._handle_trade(data)
        elif event_type == "price_change":
            await self._handle_price_change(data)
        elif event_type == "last_trade_price":
            await self._handle_last_trade_price(data)
        elif event_type == "user_order":
            self.emit("user_order", data)
        elif event_type == "user_trade":
            self.emit("user_trade", data)

        self.emit("message", data)

    async def _handle_live_data_message(self, data: Dict[str, Any]):
        """处理 Live Data WebSocket 消息"""
        topic = data.get("topic")
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if topic == "activity":
            if msg_type in ("trades", "orders_matched"):
                if not hasattr(self, "_activity_count"):
                    self._activity_count = 0
                    logger.info("[Activity] First activity message received, type=%s", msg_type)
                self._activity_count += 1
                if self._activity_count % 100 == 1:
                    logger.info(
                        "[Activity] message #%d: type=%s, conditionId=%s",
                        self._activity_count, msg_type, payload.get("conditionId", "N/A"),
                    )

                self.emit("activity_trade", payload)

                for sub_data in self._subscriptions.values():
                    if sub_data.get("type") == "activity":
                        handler = sub_data["handlers"].get("on_trade")
                        if handler:
                            import inspect
                            if inspect.iscoroutinefunction(handler):
                                await handler(payload)
                            else:
                                handler(payload)

        elif topic == "clob_market":
            if msg_type == "agg_orderbook":
                await self._handle_orderbook_live_data(payload)
            elif msg_type == "last_trade_price":
                await self._handle_last_trade_price_live_data(payload)
            elif msg_type == "price_change":
                await self._handle_price_change_live_data(payload)

        elif topic == "crypto_prices":
            if msg_type == "update":
                self.emit("crypto_price", payload)

        self.emit("message", data)

    async def _handle_orderbook_live_data(self, payload: Dict[str, Any]):
        """处理 Live Data 格式的订单簿"""
        await self._handle_orderbook({"event_type": "book", **payload})

    async def _handle_last_trade_price_live_data(self, payload: Dict[str, Any]):
        """处理 Live Data 格式的最新成交价"""
        await self._handle_last_trade_price({"event_type": "last_trade_price", **payload})

    async def _handle_price_change_live_data(self, payload: Dict[str, Any]):
        """处理 Live Data 格式的价格变化"""
        await self._handle_price_change({"event_type": "price_change", **payload})

    async def _handle_orderbook(self, data: Dict[str, Any]):
        """处理订单簿更新"""
        asset_id = data.get("asset_id")
        if not asset_id:
            return

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if not hasattr(self, "_orderbook_debug_count"):
            self._orderbook_debug_count = 0

        if self._orderbook_debug_count < 10:
            logger.debug(f"[WS-ORDERBOOK] {asset_id[:20]}...")
            logger.debug(f"  Bids ({len(bids)}): {bids[:3]}")
            logger.debug(f"  Asks ({len(asks)}): {asks[:3]}")
            self._orderbook_debug_count += 1

        orderbook = {
            "asset_id": asset_id,
            "bids": bids,
            "asks": asks,
            "timestamp": data.get("timestamp"),
        }

        subscribed_assets = set()
        for sub_data in self._subscriptions.values():
            subscribed_assets.update(sub_data.get("assets", []))

        if asset_id not in subscribed_assets:
            logger.debug(f"[WS-DEBUG] 收到未订阅token的orderbook: {asset_id[:20]}...")

        if orderbook["bids"]:
            best_bid = float(orderbook["bids"][-1]["price"])
            self._price_cache[f"{asset_id}_bid"] = best_bid

            if not hasattr(self, "_debug_price_count"):
                self._debug_price_count = {}
            if asset_id not in self._debug_price_count:
                self._debug_price_count[asset_id] = 0

            if self._debug_price_count[asset_id] < 5:
                logger.info(f"[WS-PRICE] {asset_id[:20]}... Bid={best_bid:.4f}")
                self._debug_price_count[asset_id] += 1

        if orderbook["asks"]:
            self._price_cache[f"{asset_id}_ask"] = float(orderbook["asks"][-1]["price"])

        self.emit("orderbook", orderbook)

        for sub_data in self._subscriptions.values():
            if asset_id in sub_data.get("assets", []):
                handler = sub_data["handlers"].get("on_orderbook")
                if handler:
                    handler(orderbook)

                price_handler = sub_data["handlers"].get("on_price")
                if price_handler and orderbook["bids"] and orderbook["asks"]:
                    best_bid = float(orderbook["bids"][-1]["price"])
                    best_ask = float(orderbook["asks"][-1]["price"])

                    price_update = {
                        "asset_id": asset_id,
                        "price": best_bid,
                        "bid": best_bid,
                        "ask": best_ask,
                        "event_type": "book",
                    }
                    asyncio.create_task(price_handler(price_update))

    async def _handle_trade(self, data: Dict[str, Any]):
        """处理交易"""
        trade = {
            "id": data.get("id"),
            "asset_id": data.get("asset_id"),
            "market_id": data.get("market_id"),
            "side": data.get("side"),
            "price": float(data.get("price", 0)),
            "size": float(data.get("size", 0)),
            "timestamp": data.get("timestamp"),
            "trader_address": data.get("trader_address"),
        }

        self._price_cache[trade["asset_id"]] = trade["price"]
        self.emit("trade", trade)

        for sub_data in self._subscriptions.values():
            handler = sub_data["handlers"].get("on_trade")
            if handler:
                handler(trade)

    async def _handle_price_change(self, data: Dict[str, Any]):
        """处理价格变化事件"""
        price_changes = data.get("price_changes", [])

        for change in price_changes:
            asset_id = str(change.get("asset_id", ""))
            if not asset_id:
                continue

            try:
                price = float(change.get("price", 0))
                size = float(change.get("size", 0))
                best_bid = float(change.get("best_bid", 0) or data.get("best_bid", 0))
                best_ask = float(change.get("best_ask", 0) or data.get("best_ask", 0))
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            self._price_cache[asset_id] = price

            price_update = {
                "asset_id": asset_id,
                "price": best_bid if best_bid > 0 else price,
                "size": size,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "side": change.get("side", ""),
                "timestamp": data.get("timestamp"),
                "event_type": "price_change",
            }

            self.emit("price_update", price_update)

            for sub_data in self._subscriptions.values():
                if asset_id in sub_data.get("assets", []):
                    handler = sub_data["handlers"].get("on_price")
                    if handler:
                        await handler(price_update)

    async def _handle_last_trade_price(self, data: Dict[str, Any]):
        """处理最后成交价"""
        asset_id = data.get("asset_id")
        price = float(data.get("price", 0))

        if asset_id:
            self._price_cache[asset_id] = price

        price_update = {
            "asset_id": asset_id,
            "price": price,
            "timestamp": data.get("timestamp"),
            "event_type": "last_trade_price",
        }

        self.emit("price_update", price_update)

        for sub_data in self._subscriptions.values():
            if asset_id in sub_data.get("assets", []):
                handler = sub_data["handlers"].get("on_price")
                if handler:
                    await handler(price_update)

    # ========================================================================
    # 订阅管理
    # ========================================================================

    async def subscribe_market(
        self,
        yes_token_id: str,
        no_token_id: str,
        handlers: Dict[str, Callable] = None,
    ) -> str:
        """订阅市场数据"""
        handlers = handlers or {}

        message = {
            "type": "subscribe",
            "channel": "market",
            "markets": [yes_token_id, no_token_id],
        }

        self._send_subscription(message)

        sub_id = f"market_{yes_token_id}_{no_token_id}"
        self._subscriptions[sub_id] = {
            "type": "market",
            "message": message,
            "assets": [yes_token_id, no_token_id],
            "handlers": handlers,
        }

        return sub_id

    async def subscribe_all_activity(
        self,
        handlers: Dict[str, Callable] = None,
    ) -> str:
        """订阅所有交易活动"""
        handlers = handlers or {}

        message = {
            "subscriptions": [
                {"topic": "activity", "type": "trades"},
                {"topic": "activity", "type": "orders_matched"},
            ]
        }

        self._send_subscription(message)

        sub_id = "all_activity"
        self._subscriptions[sub_id] = {
            "type": "activity",
            "message": message,
            "handlers": handlers,
        }

        return sub_id

    async def subscribe_token_prices(
        self,
        token_ids: List[str],
        on_price: Callable = None,
    ) -> str:
        """订阅多个 token 的价格更新"""
        message = {
            "type": "MARKET",
            "assets_ids": token_ids,
        }

        self._send_subscription(message)

        sub_id = f"tokens_{'_'.join([t[:10] for t in token_ids[:3]])}"
        self._subscriptions[sub_id] = {
            "type": "tokens",
            "message": message,
            "assets": token_ids,
            "handlers": {"on_price": on_price} if on_price else {},
        }

        logger.info(f"[WebSocket] 订阅 {len(token_ids)} 个 token 的价格更新")
        return sub_id

    async def unsubscribe(self, sub_id: str):
        """取消订阅"""
        if sub_id not in self._subscriptions:
            return

        sub_data = self._subscriptions[sub_id]

        message = {
            "type": "unsubscribe",
            **{k: v for k, v in sub_data["message"].items() if k != "type"},
        }

        self._send_subscription(message)
        del self._subscriptions[sub_id]

    def _send_subscription(self, message: Dict[str, Any]):
        """发送订阅消息"""
        if not self._connected or not self._ws:
            logger.info("[WebSocket] 未连接，订阅将在连接建立后自动发送")
            return

        try:
            if "subscriptions" in message and "action" not in message:
                message = {"action": "subscribe", **message}

            logger.info(f"发送订阅消息: {json.dumps(message)}")
            self._ws.send(json.dumps(message))
            logger.info("[OK] 订阅消息已发送")
        except Exception as e:
            logger.error(f"[WebSocket] 发送订阅消息失败: {e}")

    async def _resubscribe_all(self):
        """重新订阅所有主题"""
        if not self._subscriptions:
            return

        await asyncio.sleep(0.5)

        for sub_id, sub_data in list(self._subscriptions.items()):
            try:
                self._send_subscription(sub_data["message"])
                logger.info(f"[WebSocket] 重新订阅: {sub_id}")
            except Exception as e:
                logger.error(f"[WebSocket] 重新订阅失败 {sub_id}: {str(e)}")

    # ========================================================================
    # 健康监控
    # ========================================================================

    async def _health_check_loop(self):
        """应用层健康监控（检测静默断开）"""
        logger.info(
            f"[Health] 健康监控已启动（检查间隔: {self._health_check_interval}s, 超时: {self._health_check_timeout}s）"
        )

        while self._connected and not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._health_check_interval)

                if not self._connected:
                    break

                current_time = time.time()
                time_since_last_message = current_time - self._last_message_time

                if time_since_last_message > self._health_check_timeout:
                    logger.warning(f"\n{'=' * 80}")
                    logger.warning("[HEALTH ALERT] 检测到静默断开！")
                    logger.warning(f"{'=' * 80}")
                    logger.warning(f"  - 最后消息时间: {time_since_last_message:.0f} 秒前")
                    logger.warning(f"  - 超时阈值: {self._health_check_timeout} 秒")
                    logger.warning(f"  - 协议层状态: connected={self._connected}")
                    logger.warning(f"  - 操作: 强制断开并重连...")
                    logger.warning(f"{'=' * 80}\n")

                    self.emit(
                        "health_check_failed",
                        {
                            "time_since_last_message": time_since_last_message,
                            "timeout": self._health_check_timeout,
                        },
                    )

                    self._reconnect_attempts = 0
                    logger.info("[Health] 触发重连并退出当前健康监控...")
                    await self.disconnect()
                    asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                logger.info("[Health] 健康监控已停止")
                break
            except Exception as e:
                logger.error(f"[Health] 健康检查错误: {e}")

    # ========================================================================
    # 价格缓存与工具方法
    # ========================================================================

    def get_cached_price(self, asset_id: str, side: str = "last") -> Optional[float]:
        """获取缓存的价格"""
        if side == "last":
            return self._price_cache.get(asset_id)
        else:
            return self._price_cache.get(f"{asset_id}_{side}")

    def clear_price_cache(self):
        """清除价格缓存"""
        self._price_cache.clear()

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected

    def get_subscriptions(self) -> List[str]:
        """获取所有订阅 ID"""
        return list(self._subscriptions.keys())

    async def close(self):
        """关闭服务"""
        await self.disconnect()


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 核心类
    "RealtimeService",
    "EventEmitter",
    "ProxyHelper",
    "ProxyConfig",
    "PolymarketError",
    "ErrorCode",
    # 枚举
    "WebSocketTopic",
    "MessageType",
]
