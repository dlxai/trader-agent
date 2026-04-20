"""
WebSocket 处理器 - 实时价格订阅
管理 Polymarket WebSocket 连接，实时接收价格更新
"""

import asyncio
import json
import logging
from typing import Dict, Set, Callable, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp


logger = logging.getLogger(__name__)


@dataclass
class WebSocketConfig:
    """WebSocket 配置"""
    url: str = "wss://ws.prd.polymarket.com"
    reconnect_interval_ms: int = 5000
    max_reconnect_attempts: int = 10
    heartbeat_interval_ms: int = 30000
    fallback_to_http: bool = True
    http_fallback_interval_ms: int = 5000


class WebSocketHandler:
    """
    WebSocket 处理器

    职责：
    1. 管理 WebSocket 连接（连接、重连、心跳）
    2. 订阅/取消订阅 token 价格
    3. 实时接收价格更新
    4. HTTP 回退机制（WebSocket 失败时）
    5. 自动重连和错误恢复
    """

    def __init__(
        self,
        config: Dict,
        on_price_update: Callable[[str, float], None],
        on_connection_status: Callable[[bool], None] = None,
    ):
        self.config = WebSocketConfig(**config)
        self.on_price_update = on_price_update
        self.on_connection_status = on_connection_status

        # WebSocket 连接
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 状态
        self._running = False
        self._connected = False
        self._reconnect_attempts = 0
        self._subscribed_tokens: Set[str] = set()
        self._last_price_update: Dict[str, datetime] = {}

        # HTTP 回退
        self._http_fallback_task: Optional[asyncio.Task] = None
        self._http_fallback_active = False

        # 统计
        self._messages_received = 0
        self._price_updates = 0
        self._reconnects = 0

    async def start(self):
        """启动 WebSocket 处理器"""
        if self._running:
            logger.warning("WebSocket handler is already running")
            return

        self._running = True
        logger.info(f"Starting WebSocket handler (url: {self.config.url})")

        # 创建 aiohttp session
        self._session = aiohttp.ClientSession(
            headers={
                "User-Agent": "WestGardeng-Trader/1.0",
                "Accept": "application/json",
            }
        )

        # 启动连接任务
        self._connection_task = asyncio.create_task(self._connection_loop())

    async def stop(self):
        """停止 WebSocket 处理器"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping WebSocket handler...")

        # 取消任务
        tasks = [
            self._connection_task,
            self._heartbeat_task,
            self._http_fallback_task,
        ]

        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 关闭 WebSocket 连接
        if self._ws:
            await self._ws.close()
            self._ws = None

        # 关闭 session
        if self._session:
            await self._session.close()
            self._session = None

        self._connected = False
        if self.on_connection_status:
            self.on_connection_status(False)

        # 输出统计
        logger.info(
            f"WebSocket handler stopped. Stats: "
            f"messages={self._messages_received}, "
            f"price_updates={self._price_updates}, "
            f"reconnects={self._reconnects}"
        )

    def subscribe_token(self, token_id: str):
        """订阅 token 价格"""
        if token_id in self._subscribed_tokens:
            return

        self._subscribed_tokens.add(token_id)
        logger.debug(f"Subscribed to token: {token_id}")

        # 如果已连接，发送订阅消息
        if self._connected and self._ws:
            asyncio.create_task(self._send_subscription(token_id))

    def unsubscribe_token(self, token_id: str):
        """取消订阅 token 价格"""
        if token_id not in self._subscribed_tokens:
            return

        self._subscribed_tokens.remove(token_id)
        logger.debug(f"Unsubscribed from token: {token_id}")

        # 如果已连接，发送取消订阅消息
        if self._connected and self._ws:
            asyncio.create_task(self._send_unsubscription(token_id))

    async def _connection_loop(self):
        """连接主循环 - 管理 WebSocket 连接和自动重连"""
        while self._running:
            try:
                # 尝试连接
                await self._connect()

                # 连接成功，重置重连计数
                self._reconnect_attempts = 0

                # 处理消息
                await self._handle_messages()

            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            finally:
                # 清理连接状态
                await self._cleanup_connection()

                # 检查是否应该重连
                if not self._running:
                    break

                # 重连延迟（指数退避）
                self._reconnect_attempts += 1
                if self._reconnect_attempts > self.config.max_reconnect_attempts:
                    logger.error(f"Max reconnect attempts ({self.config.max_reconnect_attempts}) reached")
                    if self.config.fallback_to_http:
                        await self._start_http_fallback()
                    break

                delay_ms = min(
                    self.config.reconnect_interval_ms * (2 ** (self._reconnect_attempts - 1)),
                    60000  # 最大 60 秒
                )
                logger.info(f"Reconnecting in {delay_ms}ms (attempt {self._reconnect_attempts})")
                await asyncio.sleep(delay_ms / 1000)

    async def _connect(self):
        """建立 WebSocket 连接"""
        if not self._session:
            raise RuntimeError("Session not initialized")

        logger.info(f"Connecting to WebSocket: {self.config.url}")

        self._ws = await self._session.ws_connect(
            self.config.url,
            heartbeat=self.config.heartbeat_interval_ms / 1000,
            autoping=True,
        )

        self._connected = True
        if self.on_connection_status:
            self.on_connection_status(True)

        logger.info("WebSocket connected")

        # 重新订阅所有 token
        for token_id in self._subscribed_tokens:
            await self._send_subscription(token_id)

        # 启动心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _cleanup_connection(self):
        """清理连接状态"""
        self._connected = False
        if self.on_connection_status:
            self.on_connection_status(False)

        # 取消心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # 关闭 WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            finally:
                self._ws = None

    async def _handle_messages(self):
        """处理 WebSocket 消息"""
        async for msg in self._ws:
            if not self._running:
                break

            self._messages_received += 1

            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._process_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("WebSocket connection closed by server")
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {msg.data}")
                break

    async def _process_message(self, data: Dict):
        """处理单个消息"""
        # 根据 Polymarket WebSocket 消息格式处理
        # 这里需要根据实际的消息格式进行调整

        msg_type = data.get("type", "")

        if msg_type == "price":
            # 价格更新消息
            token_id = data.get("token_id")
            price = data.get("price")

            if token_id and price:
                self._price_updates += 1
                self._last_price_update[token_id] = datetime.now()

                # 触发价格更新回调
                if self.on_price_update:
                    try:
                        self.on_price_update(token_id, price)
                    except Exception as e:
                        logger.error(f"Error in price update callback: {e}")

        elif msg_type == "trade":
            # 交易消息
            logger.debug(f"Trade message received: {data}")

        else:
            logger.debug(f"Unknown message type: {msg_type}")

    async def _send_subscription(self, token_id: str):
        """发送订阅消息"""
        if not self._ws:
            return

        try:
            # 根据 Polymarket WebSocket 协议发送订阅消息
            message = {
                "type": "subscribe",
                "channel": "price",
                "token_id": token_id,
            }
            await self._ws.send_json(message)
            logger.debug(f"Sent subscription for token: {token_id}")

        except Exception as e:
            logger.error(f"Error sending subscription: {e}")

    async def _send_unsubscription(self, token_id: str):
        """发送取消订阅消息"""
        if not self._ws:
            return

        try:
            message = {
                "type": "unsubscribe",
                "channel": "price",
                "token_id": token_id,
            }
            await self._ws.send_json(message)
            logger.debug(f"Sent unsubscription for token: {token_id}")

        except Exception as e:
            logger.error(f"Error sending unsubscription: {e}")

    async def _heartbeat_loop(self):
        """心跳循环 - 保持连接活跃"""
        while self._running and self._connected:
            try:
                # 发送 ping 消息
                if self._ws:
                    await self._ws.ping()

                # 检查上次更新时间
                for token_id, last_update in list(self._last_price_update.items()):
                    elapsed = (datetime.now() - last_update).total_seconds()

                    # 如果超过 10 秒没有更新，触发 HTTP 回退
                    if elapsed > 10 and self.config.fallback_to_http:
                        logger.warning(
                            f"No price update for {token_id} in {elapsed:.1f}s, "
                            "activating HTTP fallback"
                        )
                        await self._start_http_fallback(token_id)

                # 等待下一次心跳
                await asyncio.sleep(self.config.heartbeat_interval_ms / 1000)

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5)

    async def _start_http_fallback(self, token_id: str):
        """启动 HTTP 回退机制"""
        if self._http_fallback_active:
            return

        self._http_fallback_active = True
        logger.info(f"Starting HTTP fallback for token: {token_id}")

        # 取消之前的回退任务
        if self._http_fallback_task:
            self._http_fallback_task.cancel()

        # 启动新的回退任务
        self._http_fallback_task = asyncio.create_task(
            self._http_fallback_loop(token_id)
        )

    async def _http_fallback_loop(self, token_id: str):
        """HTTP 回退循环"""
        try:
            while self._running and self._http_fallback_active:
                try:
                    # 通过 HTTP API 获取价格
                    price = await self._fetch_price_http(token_id)

                    if price:
                        # 触发价格更新回调
                        if self.on_price_update:
                            self.on_price_update(token_id, price)

                        logger.debug(f"HTTP fallback price for {token_id}: {price}")

                except Exception as e:
                    logger.error(f"Error in HTTP fallback: {e}")

                # 等待下一次轮询
                await asyncio.sleep(self.config.http_fallback_interval_ms / 1000)

        except asyncio.CancelledError:
            logger.info("HTTP fallback loop cancelled")

        finally:
            self._http_fallback_active = False

    async def _fetch_price_http(self, token_id: str) -> Optional[float]:
        """通过 HTTP API 获取价格"""
        # TODO: 实现实际的 HTTP API 调用
        # 这里需要调用 Polymarket REST API

        # 模拟实现
        await asyncio.sleep(0.01)
        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "connected": self._connected,
            "reconnect_attempts": self._reconnect_attempts,
            "messages_received": self._messages_received,
            "price_updates": self._price_updates,
            "reconnects": self._reconnects,
            "subscribed_tokens": len(self._subscribed_tokens),
            "http_fallback_active": self._http_fallback_active,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
        }
