"""
价格实时监控器
通过 Polymarket Market Channel WebSocket 监控价格变化，触发止损止盈
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

import websockets

logger = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    """价格更新"""
    token_id: str
    market_id: str
    price: float
    timestamp: datetime
    change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceAlert:
    """价格警报"""
    token_id: str
    alert_type: str  # "stop_loss", "take_profit", "trailing_stop", "high_price"
    current_price: float
    trigger_price: float
    threshold: float
    position_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class PriceMonitor:
    """
    价格实时监控器

    职责：
    1. 通过 WebSocket 实时获取价格更新
    2. 监控持仓代币的价格变化
    3. 触发止损、止盈、移动止损
    4. 记录价格历史用于分析

    WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/market
    """

    def __init__(
        self,
        ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market",
        api_key: Optional[str] = None,
        on_price_update: Optional[Callable[[PriceUpdate], None]] = None,
        on_price_alert: Optional[Callable[[PriceAlert], None]] = None,
    ):
        self.ws_url = ws_url
        self.api_key = api_key
        self.on_price_update = on_price_update
        self.on_price_alert = on_price_alert

        # WebSocket 连接
        self._ws = None
        self._running = False
        self._reconnect_interval = 5
        self._max_reconnect_attempts = 10

        # 价格缓存
        self._price_cache: Dict[str, PriceUpdate] = {}
        self._price_history: Dict[str, List[PriceUpdate]] = {}
        self._max_history_size = 1000

        # 监控的代币
        self._subscribed_tokens: set = set()

        # 统计
        self._update_count = 0
        self._alert_count = 0
        self._last_update_time: Optional[datetime] = None

        logger.info(f"PriceMonitor initialized (ws_url: {ws_url})")

    # ==================== WebSocket 连接管理 ====================

    async def start(self):
        """启动监控"""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info("Starting PriceMonitor...")

        # 启动 WebSocket 连接循环
        asyncio.create_task(self._ws_connection_loop())

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping PriceMonitor...")

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

                # 建立 WebSocket 连接
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                self._ws = await websockets.connect(
                    self.ws_url,
                    extra_headers=headers if headers else None
                )

                reconnect_attempts = 0
                logger.info("WebSocket connected")

                # 恢复订阅
                if self._subscribed_tokens:
                    await self._resubscribe_tokens()

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

    async def _resubscribe_tokens(self):
        """恢复订阅"""
        if not self._ws or not self._subscribed_tokens:
            return

        try:
            subscribe_msg = {
                "type": "subscribe",
                "tokens": list(self._subscribed_tokens)
            }
            await self._ws.send(json.dumps(subscribe_msg))
            logger.debug(f"Resubscribed to {len(self._subscribed_tokens)} tokens")
        except Exception as e:
            logger.error(f"Error resubscribing: {e}")

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
            msg_type = data.get("type", "")

            if msg_type == "price_update":
                await self._handle_price_update(data)
            elif msg_type == "trade":
                await self._handle_trade(data)
            elif msg_type == "order_book":
                await self._handle_order_book(data)
            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    # ==================== 价格处理 ====================

    async def _handle_price_update(self, data: Dict):
        """处理价格更新"""
        try:
            token_id = data.get("token_id")
            if not token_id:
                return

            price = float(data.get("price", 0))
            if price <= 0 or price > 1:
                logger.warning(f"Invalid price for {token_id}: {price}")
                return

            # 创建价格更新对象
            price_update = PriceUpdate(
                token_id=token_id,
                market_id=data.get("market_id", ""),
                price=price,
                timestamp=datetime.now(),
                change_24h=float(data.get("change_24h", 0)) if data.get("change_24h") else None,
                volume_24h=float(data.get("volume_24h", 0)) if data.get("volume_24h") else None,
                best_bid=float(data.get("best_bid", 0)) if data.get("best_bid") else None,
                best_ask=float(data.get("best_ask", 0)) if data.get("best_ask") else None,
                spread=float(data.get("spread", 0)) if data.get("spread") else None,
                raw_data=data
            )

            # 更新缓存
            self._update_price_cache(price_update)

            # 触发回调
            if self.on_price_update:
                await self.on_price_update(price_update)

            self._update_count += 1
            self._last_update_time = datetime.now()

            logger.debug(f"Price update for {token_id}: {price:.4f}")

        except Exception as e:
            logger.error(f"Error handling price update: {e}")

    async def _handle_trade(self, data: Dict):
        """处理成交消息"""
        # 可以在这里实现基于成交量的策略
        pass

    async def _handle_order_book(self, data: Dict):
        """处理订单簿更新"""
        # 可以在这里实现基于订单簿的策略
        pass

    def _update_price_cache(self, price_update: PriceUpdate):
        """更新价格缓存"""
        token_id = price_update.token_id

        # 更新当前价格
        self._price_cache[token_id] = price_update

        # 添加到历史
        if token_id not in self._price_history:
            self._price_history[token_id] = []

        self._price_history[token_id].append(price_update)

        # 限制历史大小
        if len(self._price_history[token_id]) > self._max_history_size:
            self._price_history[token_id] = self._price_history[token_id][-self._max_history_size:]

    # ==================== 公共接口 ====================

    async def subscribe_token(self, token_id: str):
        """订阅代币价格更新"""
        if token_id in self._subscribed_tokens:
            return

        self._subscribed_tokens.add(token_id)

        if self._ws:
            try:
                subscribe_msg = {
                    "type": "subscribe",
                    "token_id": token_id
                }
                await self._ws.send(json.dumps(subscribe_msg))
                logger.info(f"Subscribed to token: {token_id}")
            except Exception as e:
                logger.error(f"Error subscribing to token {token_id}: {e}")

    async def unsubscribe_token(self, token_id: str):
        """取消订阅代币价格更新"""
        if token_id not in self._subscribed_tokens:
            return

        self._subscribed_tokens.discard(token_id)

        if self._ws:
            try:
                unsubscribe_msg = {
                    "type": "unsubscribe",
                    "token_id": token_id
                }
                await self._ws.send(json.dumps(unsubscribe_msg))
                logger.info(f"Unsubscribed from token: {token_id}")
            except Exception as e:
                logger.error(f"Error unsubscribing from token {token_id}: {e}")

    def get_current_price(self, token_id: str) -> Optional[PriceUpdate]:
        """获取代币当前价格"""
        return self._price_cache.get(token_id)

    def get_price_history(self, token_id: str, limit: int = 100) -> List[PriceUpdate]:
        """获取代币价格历史"""
        history = self._price_history.get(token_id, [])
        return history[-limit:] if limit < len(history) else history

    def get_stats(self) -> Dict:
        """获取监控统计"""
        return {
            "is_running": self._running,
            "ws_connected": self._ws is not None and self._ws.open,
            "subscribed_tokens": len(self._subscribed_tokens),
            "price_cache_size": len(self._price_cache),
            "update_count": self._update_count,
            "alert_count": self._alert_count,
            "last_update_time": self._last_update_time.isoformat() if self._last_update_time else None,
        }
