"""
Sports WebSocket Service

Polymarket Sports WebSocket 实时比分数据服务

提供：
- 实时比分更新
- 比赛状态变化（开始、结束、暂停等）
- 赔率变化
- 自动重连
- 代理支持

WebSocket Endpoint: wss://ws-live-data.polymarket.com

参考文档: https://docs.polymarket.com/market-data/websocket/sports
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

class MatchStatus(str, Enum):
    """比赛状态"""
    SCHEDULED = "scheduled"      # 已安排
    LIVE = "live"                # 进行中
    HALFTIME = "halftime"        # 半场休息
    PAUSED = "paused"            # 暂停
    FINISHED = "finished"        # 已结束
    CANCELLED = "cancelled"      # 取消
    POSTPONED = "postponed"      # 延期


class SportType(str, Enum):
    """体育类型"""
    SOCCER = "soccer"            # 足球
    BASKETBALL = "basketball"    # 篮球
    TENNIS = "tennis"            # 网球
    BASEBALL = "baseball"        # 棒球
    AMERICAN_FOOTBALL = "american_football"  # 美式足球
    HOCKEY = "hockey"            # 冰球
    CRICKET = "cricket"          # 板球
    ESPORTS = "esports"          # 电子竞技


@dataclass
class Score:
    """比分数据"""
    home: int = 0
    away: int = 0
    home_ht: Optional[int] = None  # 半场主队比分
    away_ht: Optional[int] = None  # 半场客队比分
    home_ot: Optional[int] = None  # 加时主队比分
    away_ot: Optional[int] = None  # 加时客队比分


@dataclass
class MatchTime:
    """比赛时间"""
    current_minute: int = 0        # 当前分钟
    stoppage_time: int = 0         # 补时分钟
    period: int = 1                # 当前节/半场
    total_periods: int = 2         # 总节/半场数
    timestamp: Optional[int] = None  # 服务器时间戳


@dataclass
class Team:
    """球队信息"""
    id: str
    name: str
    short_name: str
    logo_url: Optional[str] = None


@dataclass
class MarketOdds:
    """市场赔率"""
    home_price: float = 0.0        # 主胜价格
    away_price: float = 0.0        # 客胜价格
    draw_price: Optional[float] = None  # 平局价格（足球）
    spread: Optional[float] = None  # 让分
    total: Optional[float] = None   # 总分盘
    timestamp: int = 0


@dataclass
class MatchData:
    """完整比赛数据"""
    match_id: str
    market_id: str
    sport: SportType
    status: MatchStatus
    home_team: Team
    away_team: Team
    score: Score
    match_time: MatchTime
    odds: Optional[MarketOdds] = None
    venue: Optional[str] = None
    start_time: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreUpdateEvent:
    """比分更新事件"""
    match_id: str
    market_id: str
    timestamp: int
    old_score: Score
    new_score: Score
    scoring_team: str  # "home" or "away"
    scorer_name: Optional[str] = None
    assist_name: Optional[str] = None
    event_type: str = "goal"  # goal, penalty, own_goal, etc.


@dataclass
class MatchStatusEvent:
    """比赛状态变更事件"""
    match_id: str
    market_id: str
    timestamp: int
    old_status: MatchStatus
    new_status: MatchStatus
    reason: Optional[str] = None


# =============================================================================
# Sports WebSocket 服务
# =============================================================================

class SportsWebSocketService:
    """
    Polymarket Sports WebSocket 服务

    提供实时比分、比赛状态、赔率等数据

    WebSocket: wss://ws-live-data.polymarket.com
    """

    WS_URL = "wss://ws-live-data.polymarket.com"

    def __init__(
        self,
        proxy: Optional[str] = "http://127.0.0.1:7890",
        auto_reconnect: bool = True,
        max_reconnect_attempts: int = 5,
        ping_interval: int = 30,
    ):
        """
        初始化 Sports WebSocket 服务

        Args:
            proxy: 代理地址，默认 http://127.0.0.1:7890
            auto_reconnect: 是否自动重连
            max_reconnect_attempts: 最大重连次数
            ping_interval: Ping 间隔（秒）
        """
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

        # 订阅管理
        self._subscriptions: Dict[str, Dict[str, Any]] = {}

        # 比赛数据缓存
        self._match_cache: Dict[str, MatchData] = {}
        self._odds_cache: Dict[str, MarketOdds] = {}

        # 事件处理器
        self._handlers: Dict[str, List[Callable]] = {
            "score_update": [],
            "status_change": [],
            "odds_change": [],
            "match_start": [],
            "match_end": [],
            "message": [],
            "error": [],
        }

        logger.info(f"[SportsWebSocket] 初始化完成, proxy={proxy}")

    # ==========================================================================
    # 连接管理
    # ==========================================================================

    async def connect(self):
        """连接 WebSocket"""
        try:
            if self._connected:
                logger.info("[SportsWebSocket] 已连接，跳过")
                return

            self._event_loop = asyncio.get_event_loop()

            logger.info(f"[SportsWebSocket] 正在连接到 {self.WS_URL}...")

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

            # 等待连接建立
            for _ in range(100):
                if self._connected:
                    break
                await asyncio.sleep(0.1)
            else:
                raise ConnectionError("连接超时")

            self._last_message_time = time.time()
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info("[SportsWebSocket] 已连接")

        except Exception as e:
            self._connected = False
            logger.error(f"[SportsWebSocket] 连接失败: {e}")
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
            logger.error(f"[SportsWebSocket] run_forever 错误: {e}")
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
        logger.info("[SportsWebSocket] 正在断开...")
        self._connected = False
        self._stop_event.set()

        if self._health_check_task:
            self._health_check_task.cancel()

        if self._ws:
            self._ws.close()
            self._ws = None

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)

        logger.info("[SportsWebSocket] 已断开")

    # ==========================================================================
    # WebSocket 回调
    # ==========================================================================

    def _on_open(self, ws):
        """连接打开"""
        self._connected = True
        self._reconnect_attempts = 0
        logger.info("[SportsWebSocket] 连接已建立")

        # 重新订阅
        if self._subscriptions:
            asyncio.create_task(self._resubscribe_all())

    def _on_message(self, ws, message):
        """处理消息"""
        try:
            self._last_message_time = time.time()
            data = json.loads(message)

            # 调度异步处理
            if self._event_loop:
                asyncio.run_coroutine_threadsafe(self._handle_message(data), self._event_loop)

        except Exception as e:
            logger.error(f"[SportsWebSocket] 处理消息失败: {e}")

    def _on_error(self, ws, error):
        """错误处理"""
        logger.error(f"[SportsWebSocket] 错误: {error}")
        self._connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        logger.info(f"[SportsWebSocket] 连接关闭: {close_status_code} - {close_msg}")
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

        if msg_type == "score_update":
            await self._handle_score_update(data)
        elif msg_type == "status_change":
            await self._handle_status_change(data)
        elif msg_type == "odds_change":
            await self._handle_odds_change(data)
        elif msg_type == "match_start":
            await self._handle_match_start(data)
        elif msg_type == "match_end":
            await self._handle_match_end(data)

        # 触发通用消息处理器
        for handler in self._handlers.get("message", []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[SportsWebSocket] 消息处理器错误: {e}")

    async def _handle_score_update(self, data: Dict[str, Any]):
        """处理比分更新"""
        try:
            match_id = data.get("match_id")
            market_id = data.get("market_id")
            new_score = data.get("score", {})
            old_score = data.get("old_score", {})
            scoring_team = data.get("scoring_team")

            # 更新缓存
            if match_id in self._match_cache:
                match = self._match_cache[match_id]
                match.score.home = new_score.get("home", 0)
                match.score.away = new_score.get("away", 0)

            event = ScoreUpdateEvent(
                match_id=match_id,
                market_id=market_id,
                timestamp=data.get("timestamp", int(time.time())),
                old_score=Score(**old_score) if old_score else Score(),
                new_score=Score(**new_score) if new_score else Score(),
                scoring_team=scoring_team,
                scorer_name=data.get("scorer_name"),
                assist_name=data.get("assist_name"),
                event_type=data.get("event_type", "goal"),
            )

            # 触发事件处理器
            for handler in self._handlers.get("score_update", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"[SportsWebSocket] score_update 处理器错误: {e}")

            logger.info(f"[SportsWebSocket] 比分更新: {match_id} - {new_score}")

        except Exception as e:
            logger.error(f"[SportsWebSocket] 处理比分更新失败: {e}")

    async def _handle_status_change(self, data: Dict[str, Any]):
        """处理状态变更"""
        try:
            match_id = data.get("match_id")
            old_status = data.get("old_status")
            new_status = data.get("new_status")

            # 更新缓存
            if match_id in self._match_cache:
                match = self._match_cache[match_id]
                match.status = MatchStatus(new_status)

            event = MatchStatusEvent(
                match_id=match_id,
                market_id=data.get("market_id"),
                timestamp=data.get("timestamp", int(time.time())),
                old_status=MatchStatus(old_status),
                new_status=MatchStatus(new_status),
                reason=data.get("reason"),
            )

            # 触发事件处理器
            for handler in self._handlers.get("status_change", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"[SportsWebSocket] status_change 处理器错误: {e}")

            logger.info(f"[SportsWebSocket] 状态变更: {match_id} - {old_status} -> {new_status}")

        except Exception as e:
            logger.error(f"[SportsWebSocket] 处理状态变更失败: {e}")

    async def _handle_odds_change(self, data: Dict[str, Any]):
        """处理赔率变化"""
        try:
            market_id = data.get("market_id")
            match_id = data.get("match_id")

            odds = MarketOdds(
                home_price=data.get("home_price", 0.0),
                away_price=data.get("away_price", 0.0),
                draw_price=data.get("draw_price"),
                spread=data.get("spread"),
                total=data.get("total"),
                timestamp=data.get("timestamp", int(time.time())),
            )

            # 更新缓存
            self._odds_cache[market_id] = odds

            # 触发事件处理器
            for handler in self._handlers.get("odds_change", []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(market_id, match_id, odds)
                    else:
                        handler(market_id, match_id, odds)
                except Exception as e:
                    logger.error(f"[SportsWebSocket] odds_change 处理器错误: {e}")

            logger.debug(f"[SportsWebSocket] 赔率变更: {market_id} - home={odds.home_price:.3f}")

        except Exception as e:
            logger.error(f"[SportsWebSocket] 处理赔率变更失败: {e}")

    async def _handle_match_start(self, data: Dict[str, Any]):
        """处理比赛开始"""
        match_id = data.get("match_id")
        logger.info(f"[SportsWebSocket] 比赛开始: {match_id}")

        for handler in self._handlers.get("match_start", []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[SportsWebSocket] match_start 处理器错误: {e}")

    async def _handle_match_end(self, data: Dict[str, Any]):
        """处理比赛结束"""
        match_id = data.get("match_id")
        logger.info(f"[SportsWebSocket] 比赛结束: {match_id}")

        for handler in self._handlers.get("match_end", []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[SportsWebSocket] match_end 处理器错误: {e}")

    # ==========================================================================
    # 订阅管理
    # ==========================================================================

    async def subscribe_matches(self, match_ids: List[str]) -> str:
        """
        订阅比赛实时数据

        Args:
            match_ids: 比赛ID列表

        Returns:
            订阅ID
        """
        if not self._connected:
            raise ConnectionError("WebSocket 未连接")

        message = {
            "type": "subscribe",
            "topic": "sports",
            "filter": {
                "match_ids": match_ids,
            },
        }

        self._ws.send(json.dumps(message))

        sub_id = f"sports_{'_'.join(match_ids[:3])}"
        self._subscriptions[sub_id] = {
            "type": "sports",
            "match_ids": set(match_ids),
            "message": message,
        }

        logger.info(f"[SportsWebSocket] 订阅 {len(match_ids)} 场比赛")
        return sub_id

    async def subscribe_markets(self, market_ids: List[str]) -> str:
        """
        通过市场ID订阅相关比赛

        Args:
            market_ids: 市场ID列表

        Returns:
            订阅ID
        """
        if not self._connected:
            raise ConnectionError("WebSocket 未连接")

        message = {
            "type": "subscribe",
            "topic": "sports",
            "filter": {
                "market_ids": market_ids,
            },
        }

        self._ws.send(json.dumps(message))

        sub_id = f"sports_markets_{'_'.join(market_ids[:3])}"
        self._subscriptions[sub_id] = {
            "type": "sports",
            "market_ids": set(market_ids),
            "message": message,
        }

        logger.info(f"[SportsWebSocket] 订阅 {len(market_ids)} 个市场")
        return sub_id

    async def subscribe_all_sports(self) -> str:
        """
        订阅所有体育赛事

        Returns:
            订阅ID
        """
        if not self._connected:
            raise ConnectionError("WebSocket 未连接")

        message = {
            "type": "subscribe",
            "topic": "sports",
        }

        self._ws.send(json.dumps(message))

        sub_id = "sports_all"
        self._subscriptions[sub_id] = {
            "type": "sports",
            "message": message,
        }

        logger.info("[SportsWebSocket] 订阅所有体育比赛")
        return sub_id

    async def unsubscribe(self, sub_id: str):
        """取消订阅"""
        if sub_id not in self._subscriptions:
            return

        message = {
            "type": "unsubscribe",
            "topic": "sports",
        }

        self._ws.send(json.dumps(message))
        del self._subscriptions[sub_id]
        logger.info(f"[SportsWebSocket] 取消订阅: {sub_id}")

    async def _resubscribe_all(self):
        """重新订阅所有"""
        for sub_id, sub_data in self._subscriptions.items():
            try:
                self._ws.send(json.dumps(sub_data["message"]))
                logger.info(f"[SportsWebSocket] 重新订阅: {sub_id}")
            except Exception as e:
                logger.error(f"[SportsWebSocket] 重新订阅失败 {sub_id}: {e}")

    # ==========================================================================
    # 事件处理器注册
    # ==========================================================================

    def on(self, event: str, handler: Callable):
        """
        注册事件处理器

        Args:
            event: 事件类型
                - score_update: 比分更新
                - status_change: 状态变更
                - odds_change: 赔率变化
                - match_start: 比赛开始
                - match_end: 比赛结束
                - message: 所有消息
                - error: 错误
            handler: 处理函数
        """
        if event in self._handlers:
            self._handlers[event].append(handler)
            logger.debug(f"[SportsWebSocket] 注册处理器: {event}")

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

    def get_match(self, match_id: str) -> Optional[MatchData]:
        """获取比赛数据"""
        return self._match_cache.get(match_id)

    def get_all_matches(self) -> Dict[str, MatchData]:
        """获取所有比赛数据"""
        return self._match_cache.copy()

    def get_live_matches(self) -> List[MatchData]:
        """获取进行中比赛"""
        return [
            match for match in self._match_cache.values()
            if match.status == MatchStatus.LIVE
        ]

    def get_odds(self, market_id: str) -> Optional[MarketOdds]:
        """获取市场赔率"""
        return self._odds_cache.get(market_id)

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
                    logger.warning(f"[SportsWebSocket] 静默 {time_since_last:.0f} 秒，重连...")
                    await self._reconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SportsWebSocket] 健康检查错误: {e}")

    async def _reconnect(self):
        """重新连接"""
        if self._reconnecting:
            return

        self._reconnecting = True
        try:
            await self.disconnect()
            await asyncio.sleep(2)
            await self.connect()
            logger.info("[SportsWebSocket] 重连成功")
        except Exception as e:
            logger.error(f"[SportsWebSocket] 重连失败: {e}")
        finally:
            self._reconnecting = False

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected


# =============================================================================
# 便捷函数
# =============================================================================

async def create_sports_websocket(
    proxy: str = "http://127.0.0.1:7890",
    auto_reconnect: bool = True,
) -> SportsWebSocketService:
    """
    创建并连接 Sports WebSocket 服务

    Args:
        proxy: 代理地址
        auto_reconnect: 自动重连

    Returns:
        已连接的 SportsWebSocketService 实例
    """
    service = SportsWebSocketService(
        proxy=proxy,
        auto_reconnect=auto_reconnect,
    )
    await service.connect()
    return service


__all__ = [
    "SportsWebSocketService",
    "MatchStatus",
    "SportType",
    "Score",
    "MatchTime",
    "Team",
    "MarketOdds",
    "MatchData",
    "ScoreUpdateEvent",
    "MatchStatusEvent",
    "create_sports_websocket",
]
