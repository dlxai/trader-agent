"""Data source manager for shared WebSocket connections."""

import asyncio
import logging
import sys
import os
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any, Callable, Tuple
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger("worker.datasource")

# 添加 strategy-py 到路径
_backend_py_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_project_root = os.path.dirname(_backend_py_dir)
_strategy_py_src = os.path.join(_project_root, "strategy-py", "src")
if _strategy_py_src not in sys.path:
    sys.path.insert(0, _strategy_py_src)

from strategy.price_monitor import PriceMonitor
from strategy.activity_analyzer import ActivityAnalyzer
from strategy.sports_monitor import SportsMarketMonitor
from strategy.realtime_service import RealtimeService


@dataclass
class MarketData:
    """Market data"""
    market_id: str
    token_id: str
    yes_price: float
    no_price: float
    change_24h: float
    volume: float
    hours_to_expiry: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    bid_depth: Optional[float] = None
    ask_depth: Optional[float] = None


@dataclass
class ActivityData:
    """Activity data"""
    market_id: str
    netflow: float
    buy_volume: float
    sell_volume: float
    unique_traders: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SportsScoreData:
    """Sports score data"""
    market_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    period: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class DataSource(ABC):
    """Data source base class"""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Data source type identifier"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start data source"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop data source"""
        pass

    @abstractmethod
    async def get_market_data(self, token_id: str) -> Optional[MarketData]:
        """Get market data"""
        pass

    @abstractmethod
    async def get_activity(self, token_id: str) -> Optional[ActivityData]:
        """Get activity data"""
        pass

    @abstractmethod
    async def get_sports_score(self, token_id: str) -> Optional[SportsScoreData]:
        """Get sports score"""
        pass

    @abstractmethod
    async def subscribe(self, token_ids: List[str]) -> None:
        """Subscribe to market updates"""
        pass


class PolymarketDataSource(DataSource):
    """Polymarket data source implementation using WebSocket"""

    def __init__(self, proxy_url: Optional[str] = None):
        if proxy_url is not None:
            self._proxy_url = proxy_url if proxy_url.strip() else None
        else:
            self._proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
        self._running = False

        # WebSocket 组件
        self._price_monitor: Optional[PriceMonitor] = None
        self._activity_analyzer: Optional[ActivityAnalyzer] = None
        self._sports_monitor: Optional[SportsMarketMonitor] = None
        self._realtime_service: Optional[RealtimeService] = None

        # 订阅的 token 列表
        self._subscribed_tokens: set = set()

        # token_id -> condition_id 映射（用于 ActivityAnalyzer 查询）
        self._token_to_condition: Dict[str, str] = {}

        # condition_id -> token_id 映射（从 WebSocket activity feed 收集）
        self._condition_to_token: Dict[str, str] = {}
        self._condition_token_yes: Dict[str, str] = {}
        self._condition_token_no: Dict[str, str] = {}

        # 市场元数据缓存（token_id -> market dict，用于计算 hours_to_expiry 等）
        self._market_meta_cache: Dict[str, Dict[str, Any]] = {}

        # condition_id -> 基础市场元数据（从 WebSocket activity feed 收集，用于 cache miss 时构造最小市场）
        self._condition_meta_cache: Dict[str, Dict[str, Any]] = {}

        # 价格更新回调处理器 (token_id, price)
        self._price_handlers: List[Callable[[str, float], None]] = []

        # 热点市场回调处理器 (condition_id, window_data)
        self._hot_market_handlers: List[Callable[[str, Dict[str, Any]], None]] = []

        # 市场双窗口触发回调处理器
        self._market_trigger_handlers: List[Callable[[str, Dict[str, Any]], None]] = []

        # 事件循环引用（用于线程安全回调）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def source_type(self) -> str:
        return "polymarket"

    async def start(self) -> None:
        """Start all WebSocket connections (with timeout protection)"""
        import asyncio

        self._running = True
        self._loop = asyncio.get_running_loop()
        logger.info("PolymarketDataSource: starting WebSocket connections...")

        # 1. 启动价格监控 (持仓 token 价格)
        try:
            self._price_monitor = PriceMonitor(
                proxy_url=self._proxy_url,
                on_price_update=self._on_price_update,
            )
            await asyncio.wait_for(self._price_monitor.start(), timeout=5.0)
            logger.info("PolymarketDataSource: PriceMonitor started")
        except Exception as e:
            logger.warning("PolymarketDataSource: PriceMonitor start failed (continuing without): %s", e)
            self._price_monitor = None

        # 2. 启动 Activity 分析器 (纯数据分析器，无需 start)
        self._activity_analyzer = ActivityAnalyzer()
        # 注册热点市场回调（显著资金流时触发策略评估）
        self._activity_analyzer.on_hot_market(self._on_hot_market)
        logger.info("PolymarketDataSource: ActivityAnalyzer initialized")

        # 3. 启动 RealtimeService 订阅全市场交易活动
        try:
            self._realtime_service = RealtimeService(proxy=self._proxy_url)
            await asyncio.wait_for(self._realtime_service.connect(), timeout=5.0)
            # 注册 trade 事件处理器
            self._realtime_service.on("trade", self._on_realtime_trade)
            self._realtime_service.on("activity_trade", self._on_activity_trade)
            await asyncio.wait_for(self._realtime_service.subscribe_all_activity(), timeout=5.0)
            logger.info("PolymarketDataSource: RealtimeService connected")
        except Exception as e:
            logger.warning("PolymarketDataSource: RealtimeService start failed (continuing without): %s", e)
            self._realtime_service = None

        # 4. 启动 Sports 比分监控
        try:
            self._sports_monitor = SportsMarketMonitor(proxy_url=self._proxy_url)
            await asyncio.wait_for(self._sports_monitor.start(), timeout=5.0)
            logger.info("PolymarketDataSource: SportsMonitor started")
        except Exception as e:
            logger.warning("PolymarketDataSource: SportsMonitor start failed (continuing without): %s", e)
            self._sports_monitor = None

        logger.info("PolymarketDataSource: startup completed")

    def _on_realtime_trade(self, trade: Dict[str, Any]) -> None:
        """Handle trade from RealtimeService, forward to ActivityAnalyzer."""
        if not self._activity_analyzer:
            return
        # Adapt RealtimeService trade format to ActivityAnalyzer format
        adapted = {
            "condition_id": trade.get("market_id") or trade.get("conditionId") or trade.get("asset_id", ""),
            "slug": "",
            "title": "",
            "trader_address": trade.get("trader_address", ""),
            "amount": trade.get("size", 0),
            "side": trade.get("side", "BUY").upper(),
            "outcome": "YES" if trade.get("side", "").lower() == "buy" else "NO",
            "price": trade.get("price", 0.5),
        }
        self._activity_analyzer.process_trade(adapted)

    def _on_activity_trade(self, payload: Dict[str, Any]) -> None:
        """Handle activity trade from Live Data WebSocket."""
        if not self._activity_analyzer:
            return
        # Log full payload keys once to understand the data format
        if not hasattr(self, "_activity_payload_logged"):
            self._activity_payload_logged = True
            logger.info("[Activity] payload keys: %s", list(payload.keys()))
            # Print a redacted sample of the first payload
            sample = {k: (v if k in ("conditionId", "assetId", "tokenId", "marketId", "side", "outcome", "price", "slug", "title") else "...") for k, v in payload.items()}
            logger.info("[Activity] payload sample: %s", sample)

        # Live Data activity format uses camelCase conditionId
        # 'asset' field is the CLOB token_id (asset_id)
        adapted = {
            "condition_id": payload.get("conditionId") or payload.get("market_id") or payload.get("condition_id", ""),
            "asset_id": payload.get("asset") or payload.get("assetId") or payload.get("asset_id") or payload.get("tokenId") or payload.get("token_id") or "",
            "slug": payload.get("slug", ""),
            "title": payload.get("title", ""),
            "trader_address": payload.get("trader_address", ""),
            "amount": payload.get("amount") or payload.get("size", 0),
            "side": (payload.get("side") or "BUY").upper(),
            "outcome": payload.get("outcome", "YES"),
            "price": payload.get("price", 0.5),
        }
        if adapted["condition_id"]:
            logger.debug("[Activity] processing trade for %s, asset_id=%s, side=%s, amount=%s", adapted["condition_id"], adapted.get("asset_id") or "N/A", adapted["side"], adapted["amount"])
            cid = adapted["condition_id"]
            asset = adapted.get("asset_id")
            if asset:
                self._condition_to_token[cid] = asset
                outcome = adapted.get("outcome", "YES").upper()
                if outcome in ("YES", "Y", "UP"):
                    self._condition_token_yes[cid] = asset
                elif outcome in ("NO", "N", "DOWN"):
                    self._condition_token_no[cid] = asset
            # Cache minimal metadata for cache-miss recovery
            if cid not in self._condition_meta_cache:
                self._condition_meta_cache[cid] = {}
            meta = self._condition_meta_cache[cid]
            if adapted.get("slug"):
                meta["slug"] = adapted["slug"]
            if adapted.get("title"):
                meta["question"] = adapted["title"]
            if asset:
                meta.setdefault("tokens", [])
                # Deduplicate tokens by asset id
                existing = {t.get("token_id") or t.get("clobTokenId") for t in meta["tokens"]}
                if asset not in existing:
                    outcome_label = adapted.get("outcome", "Yes")
                    meta["tokens"].append({"token_id": asset, "outcome": outcome_label})
        self._activity_analyzer.process_trade(adapted)

    async def stop(self) -> None:
        """Stop all WebSocket connections"""
        self._running = False
        logger.info("PolymarketDataSource: stopping WebSocket connections...")

        if self._price_monitor:
            await self._price_monitor.stop()
            logger.info("PolymarketDataSource: PriceMonitor stopped")

        if self._realtime_service:
            await self._realtime_service.close()
            logger.info("PolymarketDataSource: RealtimeService closed")

        if self._sports_monitor:
            await self._sports_monitor.stop()
            logger.info("PolymarketDataSource: SportsMonitor stopped")

        logger.info("PolymarketDataSource: all components stopped")

    async def subscribe(self, token_ids: List[str]) -> None:
        """Subscribe to market updates (additive — does NOT unsubscribe existing)."""
        new_tokens = set(token_ids) - self._subscribed_tokens
        if not new_tokens:
            return
        logger.info("PolymarketDataSource: subscribing %d new tokens", len(new_tokens))
        for token_id in new_tokens:
            if self._price_monitor:
                await self._price_monitor.subscribe_token(token_id)
            self._subscribed_tokens.add(token_id)
        logger.info("PolymarketDataSource: total subscribed tokens = %d", len(self._subscribed_tokens))

    def update_market_meta(self, token_id: str, market_meta: Dict[str, Any]) -> None:
        """Cache market metadata (endDate, condition_id, etc.) for expiry calculation.

        Called by strategy_runner when Gamma market list is fetched.
        """
        if not token_id or not market_meta:
            return
        self._market_meta_cache[token_id] = market_meta

        # Also maintain token -> condition mapping for ActivityAnalyzer
        condition_id = market_meta.get("conditionId") or market_meta.get("condition_id")
        if condition_id:
            self._token_to_condition[token_id] = condition_id

    def get_condition_token_map(self) -> Dict[str, str]:
        """Return condition_id -> token_id map built from WebSocket activity feed."""
        return self._condition_to_token.copy()

    def get_condition_tokens(self, condition_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (yes_token_id, no_token_id) for a condition_id from WebSocket feed."""
        yes_tid = self._condition_token_yes.get(condition_id)
        no_tid = self._condition_token_no.get(condition_id)
        # Fallback: if only one side known, try to infer from single mapping
        if not yes_tid and not no_tid:
            single = self._condition_to_token.get(condition_id)
            if single:
                # We don't know which side; return as yes to allow price lookup
                yes_tid = single
        return (yes_tid, no_tid)

    def get_condition_meta(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """Return minimal market metadata from WebSocket feed for cache-miss recovery."""
        return self._condition_meta_cache.get(condition_id)

    def _get_hours_to_expiry(self, token_id: str) -> float:
        """Calculate hours to expiry from cached market metadata."""
        meta = self._market_meta_cache.get(token_id)
        if not meta:
            return 0.0
        end_date_str = meta.get("endDate")
        if not end_date_str:
            return 0.0
        try:
            end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            hours = (end_dt - datetime.utcnow()).total_seconds() / 3600
            return max(0.0, hours)
        except Exception:
            return 0.0

    def register_sports_position(
        self,
        position_id: str,
        market_id: str,
        entry_price: float,
        stop_loss_pct: float = 0.10,
        game_id: Optional[str] = None,
        side: str = "yes",
    ) -> None:
        """Register a sports market position for dynamic stop-loss via score events.

        SportsMarketMonitor will listen for score updates (goals, red cards, etc.)
        and dynamically tighten stop-loss when adverse events occur.

        Args:
            game_id: Polymarket sports game ID (used to match WebSocket score updates).
                     Required because the sports WS feed uses gameId, not market conditionId.
            side: Position direction ("yes" or "no").
        """
        if self._sports_monitor:
            self._sports_monitor.add_position_monitoring(
                position_id=position_id,
                market_id=market_id,
                game_id=game_id,
                entry_price=entry_price,
                original_stop_loss=stop_loss_pct,
                side=side,
            )

    def unregister_sports_position(self, position_id: str) -> None:
        """Remove a sports market position from dynamic monitoring."""
        if self._sports_monitor:
            self._sports_monitor.remove_position_monitoring(position_id)

    def get_combined_sports_exit_signal(
        self, position_id: str, market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Combined sports score + activity flow exit signal.

        SportsMonitor detects score events (goals, red cards, etc.) and adjusts
        stop-loss. This method combines that with ActivityAnalyzer flow data
        to decide: exit immediately, exit, or hold with tighter stop-loss.
        """
        if not self._sports_monitor:
            return None

        # 1. Check if sports monitor has adjusted stop-loss for this position
        dyn_sl = self._sports_monitor._dynamic_stop_loss.get(position_id)
        if not dyn_sl or not dyn_sl.adjustment_history:
            return None

        last_adj = dyn_sl.adjustment_history[-1]
        # Only care about recent adjustments (within last 60 seconds)
        from datetime import datetime
        adj_time = datetime.fromisoformat(last_adj["timestamp"])
        if (datetime.utcnow() - adj_time).total_seconds() > 60:
            return None

        # 2. Get flow data from ActivityAnalyzer
        flow = 0
        if self._activity_analyzer:
            ma = self._activity_analyzer.get_market_by_condition(market_id)
            if ma:
                flow = ma.net_flow

        # 3. Combined decision
        if last_adj["new_stop_loss"] < last_adj["old_stop_loss"]:
            # Stop-loss tightened by sports event
            if flow < -2000:
                # Large outflow confirms bad news → exit immediately
                return {
                    "action": "exit_immediately",
                    "reason": f"sports_event: {last_adj['reason']} + heavy_outflow({flow:.0f})",
                }
            elif flow < -500:
                # Moderate outflow → exit
                return {
                    "action": "exit",
                    "reason": f"sports_event: {last_adj['reason']} + outflow({flow:.0f})",
                }
            else:
                # Inflow or neutral → hold but respect tightened SL
                return {
                    "action": "hold",
                    "reason": f"sports_event: {last_adj['reason']} + flow_buffer({flow:.0f})",
                }

        return None

    def register_market_trigger_handler(self, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        """注册市场双窗口触发处理器。

        当 ActivityAnalyzer 的双窗口确认触发时，会调用所有已注册的 handler。
        Handler 签名: (condition_id: str, trigger_data: dict) -> None
        若 handler 内需要执行异步操作，请自行 asyncio.create_task()。
        """
        self._market_trigger_handlers.append(handler)

    def unregister_market_trigger_handler(self, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        """注销市场双窗口触发处理器。"""
        if handler in self._market_trigger_handlers:
            self._market_trigger_handlers.remove(handler)

    def _on_price_update(self, price_update) -> None:
        """转发 PriceMonitor 价格更新到所有注册处理器（线程安全投递到事件循环）。"""
        if not self._loop:
            return
        for handler in self._price_handlers:
            try:
                self._loop.call_soon_threadsafe(handler, price_update.token_id, price_update.price)
            except Exception as e:
                logger.error("Price handler error: %s", e)

    def register_price_handler(self, handler: Callable[[str, float], None]) -> None:
        """注册价格更新处理器。"""
        self._price_handlers.append(handler)

    def unregister_price_handler(self, handler: Callable[[str, float], None]) -> None:
        """注销价格更新处理器。"""
        if handler in self._price_handlers:
            self._price_handlers.remove(handler)

    def register_hot_market_handler(self, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        """注册热点市场处理器（当 ActivityAnalyzer 检测到显著流时触发）。"""
        self._hot_market_handlers.append(handler)

    def unregister_hot_market_handler(self, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        """注销热点市场处理器。"""
        if handler in self._hot_market_handlers:
            self._hot_market_handlers.remove(handler)

    def _on_hot_market(self, condition_id: str, window_data: Dict[str, Any]) -> None:
        """转发热点市场事件到所有注册处理器（线程安全投递到事件循环）。"""
        if not self._loop:
            return
        for handler in self._hot_market_handlers:
            try:
                self._loop.call_soon_threadsafe(handler, condition_id, window_data)
            except Exception as e:
                logger.error("Hot market handler error: %s", e)

    async def _on_dual_window_trigger(self, condition_id: str, trigger_data: Dict[str, Any]) -> None:
        """转发 ActivityAnalyzer 的双窗口触发事件到所有注册处理器。"""
        logger.info(
            "PolymarketDataSource: dual-window trigger for %s short_netflow=%.2f long_netflow=%.2f",
            condition_id,
            trigger_data.get("short_window", {}).get("net_flow", 0),
            trigger_data.get("long_window", {}).get("net_flow", 0),
        )
        for handler in self._market_trigger_handlers:
            try:
                handler(condition_id, trigger_data)
            except Exception as e:
                logger.error("Market trigger handler error: %s", e)

    async def get_market_data(self, token_id: str, fallback_timeout: int = 3) -> Optional[MarketData]:
        """Get market data from price monitor (WebSocket优先，HTTP fallback)

        Args:
            token_id: 市场 token ID
            fallback_timeout: WebSocket 无数据超时时间（秒），超过则用 HTTP
        """
        # 1. 尝试从 WebSocket 获取
        if self._price_monitor:
            price_update = self._price_monitor.get_current_price(token_id)

            if price_update:
                # 检查数据是否在超时时间内
                age = (datetime.utcnow() - (price_update.timestamp or datetime.utcnow())).total_seconds()
                if age <= fallback_timeout:
                    # WebSocket 数据新鲜，使用它
                    return MarketData(
                        market_id=token_id,
                        token_id=token_id,
                        yes_price=price_update.price,
                        no_price=1 - price_update.price,
                        change_24h=price_update.change_24h or 0,
                        volume=price_update.volume_24h or 0,
                        hours_to_expiry=self._get_hours_to_expiry(token_id),
                        timestamp=price_update.timestamp or datetime.utcnow(),
                        best_bid=price_update.best_bid,
                        best_ask=price_update.best_ask,
                        spread=price_update.spread,
                    )
                # else: WebSocket 数据太旧，用 HTTP fallback

        # 2. HTTP fallback (WebSocket 无数据或超时)
        return await self._fetch_price_http(token_id)

    async def _fetch_price_http(self, token_id: str) -> Optional[MarketData]:
        """HTTP fallback 获取价格"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0, proxy=self._proxy_url) as client:
                url = f"https://clob.polymarket.com/last-trade-price?token_id={token_id}"
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    price = float(data) if not isinstance(data, dict) else float(data.get("price", 0.5))
                    return MarketData(
                        market_id=token_id,
                        token_id=token_id,
                        yes_price=price,
                        no_price=1 - price,
                        change_24h=0,
                        volume=0,
                        hours_to_expiry=self._get_hours_to_expiry(token_id),
                        timestamp=datetime.utcnow(),
                        best_bid=None,
                        best_ask=None,
                        spread=None,
                    )
        except Exception as e:
            logger.warning("HTTP fallback failed for %s: %s", token_id, e)

        return None

    async def get_activity(self, token_id: str, window_seconds: int = 60) -> Optional[ActivityData]:
        """Get activity data from analyzer cache (time-windowed)."""
        if not self._activity_analyzer:
            return None

        # Look up condition_id from token_id mapping
        condition_id = self._token_to_condition.get(token_id, token_id)

        # Get time-windowed metrics from ActivityAnalyzer
        window_data = self._activity_analyzer.get_market_window(condition_id, window_seconds)
        if window_data:
            return ActivityData(
                market_id=condition_id,
                netflow=window_data["net_flow"],
                buy_volume=window_data["yes_volume"],
                sell_volume=window_data["no_volume"],
                unique_traders=window_data["trader_count"],
                timestamp=datetime.utcnow()
            )

        # No activity data available yet
        return None

    def get_hot_markets(self, limit: int = 50, min_score: float = 0.1) -> list[dict]:
        """Get hot markets from ActivityAnalyzer (WebSocket-driven).

        Returns market dicts compatible with strategy_runner's _get_available_markets.
        Each dict contains condition_id, slug, question, token_id, and activity metrics.
        """
        if not self._activity_analyzer:
            return []

        hot = self._activity_analyzer.get_hot_markets(limit=limit, min_score=min_score)
        result = []
        for m in hot:
            result.append({
                "condition_id": m.condition_id,
                "conditionId": m.condition_id,
                "slug": m.slug,
                "question": m.question,
                "title": m.question,
                "active": True,
                "token_id": m.token_id,
                "tokens": [{"token_id": m.token_id, "outcome": "Up"}] if m.token_id else [],
                "volume": m.total_volume,
                "current_price": m.current_price,
            })
        return result

    def is_healthy(self, max_staleness: float = 60.0) -> bool:
        """Check if price monitor is connected and data is fresh.

        Args:
            max_staleness: max seconds since last price update before considered stale.
        """
        if not self._price_monitor:
            return False
        stats = self._price_monitor.get_stats()
        if not stats.get("ws_connected"):
            return False
        last_update = stats.get("last_update_time")
        if not last_update:
            return False
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(last_update)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            staleness = (datetime.now(timezone.utc) - dt).total_seconds()
            return staleness <= max_staleness
        except Exception:
            return False

    async def get_sports_score(self, token_id: str) -> Optional[SportsScoreData]:
        """Get sports score from monitor"""
        if not self._sports_monitor:
            return None

        score_state = self._sports_monitor._score_cache.get(token_id)
        if not score_state:
            return None

        return SportsScoreData(
            market_id=token_id,
            home_team=score_state.home_team,
            away_team=score_state.away_team,
            home_score=score_state.home_score,
            away_score=score_state.away_score,
            period=score_state.game_status,
            timestamp=score_state.last_updated,
        )

    def get_sports_signal(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get sports-derived trading signal for a market (used in trigger logic)."""
        if not self._sports_monitor:
            return None
        return self._sports_monitor.get_sports_signal(token_id)


class SignalFilter:
    """Signal filter using StrategyFilters configuration"""

    def __init__(self, filters: Dict[str, Any]):
        self.min_confidence = filters.get('min_confidence', 40)
        self.min_price = filters.get('min_price', 0.5)
        self.max_price = filters.get('max_price', 0.99)
        self.max_spread = filters.get('max_spread', 3)
        self.max_slippage = filters.get('max_slippage', 2)
        self.dead_zone_enabled = filters.get('dead_zone_enabled', True)
        self.dead_zone_min = filters.get('dead_zone_min', 0.60)
        self.dead_zone_max = filters.get('dead_zone_max', 0.85)
        self.keywords_exclude = filters.get('keywords_exclude', ['o/u', 'spread'])

    def filter_market(self, market_data: MarketData) -> bool:
        """
        过滤市场数据，返回 True 表示通过过滤。
        注意：到期时间检查已集中到 ExpiryPolicy，此处不再拦截。
        """
        price = market_data.yes_price
        # 1. 价格区间过滤
        if not (self.min_price <= price <= self.max_price):
            logger.info("[FILTER] price %.4f outside range [%.2f, %.2f]", price, self.min_price, self.max_price)
            return False

        # 2. 死亡区间过滤
        if self.dead_zone_enabled:
            if self.dead_zone_min <= price <= self.dead_zone_max:
                logger.info("[FILTER] price %.4f in dead zone [%.2f, %.2f]", price, self.dead_zone_min, self.dead_zone_max)
                return False  # 在死亡区间内，不交易

        return True

    def filter_by_keywords(self, market_name: str) -> bool:
        """关键词过滤"""
        for keyword in self.keywords_exclude:
            if keyword.lower() in market_name.lower():
                return False
        return True


class TriggerChecker:
    """Trigger condition checker using StrategyTrigger configuration"""

    # 分层净流入阈值（基于 60 秒滑动窗口，参考 polymarket-agent 阶段配置）
    # 注意：Stage 阈值必须避开死亡区间 (0.60-0.85)
    STAGE_THRESHOLDS = [
        {'min_price': 0.95, 'max_price': 0.999, 'netflow': 300},   # Stage1 Sweeping: 低门槛快进出
        {'min_price': 0.90, 'max_price': 0.95, 'netflow': 150},    # Stage2 Forming: 中等门槛
        {'min_price': 0.85, 'max_price': 0.90, 'netflow': 600},    # Stage3 Early: 高门槛建仓
        # Stage4 (0.70-0.80) 已删除 - 完全在死亡区间内，死代码
    ]

    def __init__(self, trigger: Dict[str, Any], last_trigger_time: Optional[datetime] = None):
        self.price_change_threshold = trigger.get('price_change_threshold', 5)  # 5%
        self.min_trigger_interval = trigger.get('min_trigger_interval', 5)  # 5 分钟
        self.use_stage_netflow = trigger.get('use_stage_netflow', True)  # 使用分层阈值

        # 基础净流入阈值（当不使用分层时，基于 60s 窗口）
        self.base_netflow_threshold = trigger.get('activity_netflow_threshold', 150)

        self._last_trigger_time = last_trigger_time

    def check_price_trigger(self, old_price: float, new_price: float) -> bool:
        """检查价格波动是否触发"""
        if old_price == 0:
            return False

        change_pct = abs(new_price - old_price) / old_price * 100
        return change_pct >= self.price_change_threshold

    def _get_netflow_threshold(self, price: float) -> float:
        """根据价格获取对应的净流入阈值"""
        if not self.use_stage_netflow:
            return self.base_netflow_threshold

        for stage in self.STAGE_THRESHOLDS:
            if stage['min_price'] <= price <= stage['max_price']:
                return stage['netflow']
        return self.base_netflow_threshold  # 默认值

    def check_activity_trigger(self, netflow: float, price: float = 0.5) -> bool:
        """检查 Activity 是否触发（根据价格区间有不同的阈值）"""
        threshold = self._get_netflow_threshold(price)
        return abs(netflow) >= threshold

    def check_cooldown(self) -> bool:
        """检查冷却时间"""
        if not self._last_trigger_time:
            return True

        elapsed = (datetime.utcnow() - self._last_trigger_time).total_seconds() / 60
        return elapsed >= self.min_trigger_interval

    def update_trigger_time(self) -> None:
        """更新触发时间"""
        self._last_trigger_time = datetime.utcnow()


# Data source registry (supports extension)
_DATA_SOURCE_REGISTRY: Dict[str, type] = {
    "polymarket": PolymarketDataSource,
}


def register_data_source(source_type: str, source_class: type) -> None:
    """Register new data source type"""
    _DATA_SOURCE_REGISTRY[source_type] = source_class


class DataSourceManager:
    """
    Data source manager

    Manages data sources by Portfolio dimension, supports multi-source extension.
    """

    def __init__(self):
        self._sources: Dict[UUID, DataSource] = {}  # portfolio_id -> DataSource
        self._lock = asyncio.Lock()
        self._filters: Dict[UUID, SignalFilter] = {}  # portfolio_id -> Filter
        self._triggers: Dict[UUID, TriggerChecker] = {}  # portfolio_id -> Trigger

    async def get_or_create_source(
        self,
        portfolio_id: UUID,
        source_type: str = "polymarket",
        filters: Optional[Dict[str, Any]] = None,
        trigger: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> DataSource:
        """Get or create data source"""
        async with self._lock:
            if portfolio_id not in self._sources:
                logger.info("DataSourceManager: creating new source for portfolio %s type=%s", portfolio_id, source_type)
                source_class = _DATA_SOURCE_REGISTRY.get(source_type)
                if not source_class:
                    raise ValueError(f"Unknown data source type: {source_type}")

                source = source_class(**kwargs)
                await source.start()
                self._sources[portfolio_id] = source
                logger.info("DataSourceManager: source created for portfolio %s", portfolio_id)

                # 创建过滤器和触发器
                if filters:
                    self._filters[portfolio_id] = SignalFilter(filters)
                if trigger:
                    self._triggers[portfolio_id] = TriggerChecker(trigger)

            return self._sources[portfolio_id]

    def get_filter(self, portfolio_id: UUID) -> Optional[SignalFilter]:
        """Get signal filter for portfolio"""
        return self._filters.get(portfolio_id)

    def get_trigger(self, portfolio_id: UUID) -> Optional[TriggerChecker]:
        """Get trigger checker for portfolio"""
        return self._triggers.get(portfolio_id)

    def update_filter(self, portfolio_id: UUID, filters: Dict[str, Any]) -> None:
        """Update filter configuration"""
        self._filters[portfolio_id] = SignalFilter(filters)

    def update_trigger(self, portfolio_id: UUID, trigger: Dict[str, Any]) -> None:
        """Update trigger configuration"""
        self._triggers[portfolio_id] = TriggerChecker(trigger)

    async def remove_source(self, portfolio_id: UUID) -> None:
        """Remove data source"""
        async with self._lock:
            if portfolio_id in self._sources:
                logger.info("DataSourceManager: removing source for portfolio %s", portfolio_id)
                await self._sources[portfolio_id].stop()
                del self._sources[portfolio_id]

            if portfolio_id in self._filters:
                del self._filters[portfolio_id]

            if portfolio_id in self._triggers:
                del self._triggers[portfolio_id]

    async def get_all_sources(self) -> List[DataSource]:
        """Get all data sources"""
        return list(self._sources.values())

    async def close_all(self) -> None:
        """Close all data sources"""
        logger.info("DataSourceManager: closing all %d sources", len(self._sources))
        for portfolio_id, source in list(self._sources.items()):
            try:
                await source.stop()
            except Exception as e:
                logger.warning("DataSourceManager: error stopping source for portfolio %s: %s", portfolio_id, e)
        self._sources.clear()
        self._filters.clear()
        self._triggers.clear()
        logger.info("DataSourceManager: all sources closed")


# Global singleton
_data_source_manager: Optional[DataSourceManager] = None


def get_data_source_manager() -> DataSourceManager:
    """Get data source manager singleton"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager