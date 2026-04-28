"""
价格实时监控器
通过 Polymarket Market Channel WebSocket 监控价格变化，触发止损止盈
使用 websocket-client 库以统一代理支持（与 RealtimeService 一致）
"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import websocket

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
    价格实时监控器（统一使用 websocket-client 以支持代理）

    WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/market
    """

    def __init__(
        self,
        ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market",
        api_key: Optional[str] = None,
        proxy_url: Optional[str] = None,
        on_price_update: Optional[Callable[[PriceUpdate], None]] = None,
        on_price_alert: Optional[Callable[[PriceAlert], None]] = None,
    ):
        self.ws_url = ws_url
        self.api_key = api_key
        self.proxy_url = proxy_url
        self.on_price_update = on_price_update
        self.on_price_alert = on_price_alert

        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

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
        self._reconnect_attempts = 0

        logger.info("PriceMonitor initialized (ws_url: %s, proxy: %s)", ws_url, proxy_url)

    # ==================== WebSocket 连接管理 ====================

    async def start(self):
        """启动监控（异步接口，内部在线程中跑同步 WebSocketApp）"""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info("Starting PriceMonitor...")

        loop = asyncio.get_event_loop()
        self._ws_thread = threading.Thread(target=self._ws_run_loop, daemon=True)
        self._ws_thread.start()

    def _ws_run_loop(self):
        """在线程中运行 WebSocket 连接与重连"""
        self._reconnect_attempts = 0
        while self._running:
            try:
                kwargs = {"ping_interval": 30, "ping_timeout": 10}
                if self.proxy_url:
                    parsed = urlparse(self.proxy_url)
                    kwargs["http_proxy_host"] = parsed.hostname
                    kwargs["http_proxy_port"] = parsed.port or 7890
                    kwargs["proxy_type"] = "http"
                    logger.info("PriceMonitor using proxy: %s", self.proxy_url)

                self._ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                self._ws.run_forever(**kwargs)
            except Exception as e:
                logger.error("PriceMonitor run_forever error: %s", e)

            if not self._running:
                break

            self._reconnect_attempts += 1
            wait_time = min(5 * self._reconnect_attempts, 60)
            logger.info("PriceMonitor reconnecting in %ds (attempt %d)...", wait_time, self._reconnect_attempts)
            time.sleep(wait_time)

    def _on_open(self, ws):
        logger.info("PriceMonitor WebSocket connected")
        self._reconnect_attempts = 0
        self._last_update_time = datetime.now()
        with self._lock:
            if self._subscribed_tokens:
                self._resubscribe_tokens_sync()

    def _on_message(self, ws, message: str):
        try:
            self._handle_ws_message_sync(message)
        except Exception as e:
            logger.error("Error handling PriceMonitor message: %s", e)

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("PriceMonitor WebSocket closed: %s %s", close_status_code, close_msg)

    def _on_error(self, ws, error):
        logger.error("PriceMonitor WebSocket error: %s", error)

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping PriceMonitor...")

        ws = self._ws
        if ws:
            await asyncio.to_thread(ws.close)

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3)

        logger.info("PriceMonitor stopped")

    def _resubscribe_tokens_sync(self):
        """恢复订阅（同步，在 WebSocket 线程中调用）"""
        if not self._ws or not self._subscribed_tokens:
            return
        try:
            msg = json.dumps({"type": "MARKET", "assets_ids": list(self._subscribed_tokens)})
            self._ws.send(msg)
            logger.info("Resubscribed to %d tokens", len(self._subscribed_tokens))
        except Exception as e:
            logger.error("Error resubscribing: %s", e)

    # ==================== 消息处理 ====================

    def _handle_ws_message_sync(self, message: str):
        """处理单个 WebSocket 消息（同步）

        Polymarket CLOB Market Channel 使用 event_type 字段：
        - price_change / last_trade_price / book / trade
        """
        # Silently ignore empty/keepalive messages (ping/pong, control frames)
        if not message or not message.strip():
            return
        try:
            data = json.loads(message)
            if isinstance(data, list):
                return
            # Live Data wrapper format: {"topic": "...", "type": "...", "payload": {...}}
            if data.get("topic") and data.get("type"):
                payload = data.get("payload", {})
                msg_type = data.get("type")
                if msg_type in ("agg_orderbook", "book"):
                    self._handle_order_book({"event_type": "book", **payload})
                elif msg_type == "last_trade_price":
                    self._handle_last_trade_price({"event_type": "last_trade_price", **payload})
                elif msg_type == "price_change":
                    self._handle_price_change({"event_type": "price_change", **payload})
                elif msg_type == "trade":
                    self._handle_trade_ws({"event_type": "trade", **payload})
                return

            event_type = data.get("event_type")
            if event_type == "price_change":
                self._handle_price_change(data)
            elif event_type == "last_trade_price":
                self._handle_last_trade_price(data)
            elif event_type == "book":
                self._handle_order_book(data)
            elif event_type == "trade":
                self._handle_trade_ws(data)
            elif data.get("type") in ("pong", "subscribed"):
                pass
            else:
                logger.debug("Unknown WebSocket message: %s", data.get("type") or data.get("event_type"))

        except json.JSONDecodeError:
            logger.debug("Ignored non-JSON WebSocket message: %r", message[:100])
        except Exception as e:
            logger.error("Error processing WebSocket message: %s", e)

    def _handle_price_change(self, data: Dict):
        """处理价格变化事件"""
        try:
            changes = data.get("price_changes", [])
            if not changes and data.get("asset_id"):
                # Single price change format
                changes = [data]
            for change in changes:
                token_id = str(change.get("asset_id", ""))
                if not token_id:
                    continue
                price = float(change.get("price", 0))
                if price <= 0 or price > 1:
                    continue
                best_bid = float(change.get("best_bid", 0) or data.get("best_bid", 0))
                best_ask = float(change.get("best_ask", 0) or data.get("best_ask", 0))
                self._update_price(
                    token_id=token_id,
                    price=price,
                    best_bid=best_bid if best_bid > 0 else None,
                    best_ask=best_ask if best_ask > 0 else None,
                )
        except Exception as e:
            logger.error("Error handling price change: %s", e)

    def _handle_last_trade_price(self, data: Dict):
        """处理最后成交价"""
        try:
            token_id = str(data.get("asset_id", ""))
            price = float(data.get("price", 0))
            if token_id and 0 < price <= 1:
                self._update_price(token_id=token_id, price=price)
        except Exception as e:
            logger.error("Error handling last trade price: %s", e)

    def _handle_order_book(self, data: Dict):
        """处理订单簿更新"""
        try:
            token_id = str(data.get("asset_id", ""))
            if not token_id:
                return
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            best_bid = float(bids[-1]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            price = best_bid if best_bid else best_ask
            if price and 0 < price <= 1:
                self._update_price(
                    token_id=token_id,
                    price=price,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    spread=(best_ask - best_bid) if (best_bid and best_ask) else None,
                )
        except Exception as e:
            logger.error("Error handling order book: %s", e)

    def _handle_trade_ws(self, data: Dict):
        """处理交易消息"""
        try:
            token_id = str(data.get("asset_id", ""))
            price = float(data.get("price", 0))
            if token_id and 0 < price <= 1:
                self._update_price(token_id=token_id, price=price)
        except Exception as e:
            logger.error("Error handling trade: %s", e)

    def _update_price(self, token_id: str, price: float, best_bid: Optional[float] = None,
                      best_ask: Optional[float] = None, spread: Optional[float] = None):
        """统一更新价格缓存并触发回调"""
        price_update = PriceUpdate(
            token_id=token_id,
            market_id=token_id,
            price=price,
            timestamp=datetime.now(),
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
        )
        self._update_price_cache(price_update)
        if self.on_price_update:
            if asyncio.iscoroutinefunction(self.on_price_update):
                asyncio.create_task(self.on_price_update(price_update))
            else:
                self.on_price_update(price_update)
        self._update_count += 1
        self._last_update_time = datetime.now()
        logger.debug("Price update for %s: %.4f", token_id, price)

    def _update_price_cache(self, price_update: PriceUpdate):
        """更新价格缓存"""
        token_id = price_update.token_id
        self._price_cache[token_id] = price_update

        if token_id not in self._price_history:
            self._price_history[token_id] = []

        self._price_history[token_id].append(price_update)

        if len(self._price_history[token_id]) > self._max_history_size:
            self._price_history[token_id] = self._price_history[token_id][-self._max_history_size:]

    # ==================== 公共接口 ====================

    async def subscribe_token(self, token_id: str):
        """订阅代币价格更新"""
        if token_id in self._subscribed_tokens:
            return
        self._subscribed_tokens.add(token_id)

        if self._ws and self._ws.sock and self._ws.sock.connected:
            try:
                msg = json.dumps({"type": "MARKET", "assets_ids": [token_id]})
                await asyncio.wait_for(asyncio.to_thread(self._ws.send, msg), timeout=3.0)
                logger.info("Subscribed to token: %s", token_id)
            except asyncio.TimeoutError:
                logger.warning("Subscribe to token %s timed out, ws may be stale", token_id)
            except Exception as e:
                logger.error("Error subscribing to token %s: %s", token_id, e)

    async def unsubscribe_token(self, token_id: str):
        """取消订阅代币价格更新"""
        if token_id not in self._subscribed_tokens:
            return
        self._subscribed_tokens.discard(token_id)

        if self._ws and self._ws.sock and self._ws.sock.connected:
            try:
                msg = json.dumps({"type": "UNSUBSCRIBE", "assets_ids": [token_id]})
                await asyncio.wait_for(asyncio.to_thread(self._ws.send, msg), timeout=3.0)
                logger.info("Unsubscribed from token: %s", token_id)
            except asyncio.TimeoutError:
                logger.warning("Unsubscribe from token %s timed out, ws may be stale", token_id)
            except Exception as e:
                logger.error("Error unsubscribing from token %s: %s", token_id, e)

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
            "ws_connected": self._ws is not None and self._ws.sock is not None and self._ws.sock.connected,
            "subscribed_tokens": len(self._subscribed_tokens),
            "price_cache_size": len(self._price_cache),
            "update_count": self._update_count,
            "alert_count": self._alert_count,
            "last_update_time": self._last_update_time.isoformat() if self._last_update_time else None,
            "reconnect_attempts": self._reconnect_attempts,
        }
