"""Data source manager for shared WebSocket connections."""

import asyncio
import sys
import os
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

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

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        self._proxy_url = proxy_url
        self._running = False

        # WebSocket 组件
        self._price_monitor: Optional[PriceMonitor] = None
        self._activity_analyzer: Optional[ActivityAnalyzer] = None
        self._sports_monitor: Optional[SportsMarketMonitor] = None
        self._realtime_service: Optional[RealtimeService] = None

        # 订阅的 token 列表
        self._subscribed_tokens: set = set()

    @property
    def source_type(self) -> str:
        return "polymarket"

    async def start(self) -> None:
        """Start all WebSocket connections"""
        self._running = True

        # 启动价格监控 (持仓 token 价格)
        self._price_monitor = PriceMonitor(proxy_url=self._proxy_url)
        await self._price_monitor.start()

        # 启动 Activity 分析器 (纯数据分析器，无需 start)
        self._activity_analyzer = ActivityAnalyzer()

        # 启动 RealtimeService 订阅全市场交易活动，喂给 ActivityAnalyzer
        self._realtime_service = RealtimeService(proxy=self._proxy_url)
        await self._realtime_service.connect()
        # 注册 trade 事件处理器，转发给 ActivityAnalyzer
        self._realtime_service.on("trade", self._on_realtime_trade)
        self._realtime_service.on("activity_trade", self._on_activity_trade)
        # 订阅全市场交易活动
        await self._realtime_service.subscribe_all_activity()

        # 启动 Sports 比分监控
        self._sports_monitor = SportsMarketMonitor(proxy_url=self._proxy_url)
        await self._sports_monitor.start()

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
        # Live Data activity format uses camelCase conditionId
        adapted = {
            "condition_id": payload.get("conditionId") or payload.get("market_id") or payload.get("condition_id", ""),
            "slug": payload.get("slug", ""),
            "title": payload.get("title", ""),
            "trader_address": payload.get("trader_address", ""),
            "amount": payload.get("amount") or payload.get("size", 0),
            "side": (payload.get("side") or "BUY").upper(),
            "outcome": payload.get("outcome", "YES"),
            "price": payload.get("price", 0.5),
        }
        self._activity_analyzer.process_trade(adapted)

    async def stop(self) -> None:
        """Stop all WebSocket connections"""
        self._running = False

        if self._price_monitor:
            await self._price_monitor.stop()

        if self._realtime_service:
            await self._realtime_service.close()

        if self._sports_monitor:
            await self._sports_monitor.stop()

    async def subscribe(self, token_ids: List[str]) -> None:
        """Subscribe to market updates"""
        # 订阅新的 tokens
        new_tokens = set(token_ids) - self._subscribed_tokens
        for token_id in new_tokens:
            if self._price_monitor:
                await self._price_monitor.subscribe_token(token_id)
            self._subscribed_tokens.add(token_id)

        # 取消订阅不再需要的 tokens
        old_tokens = self._subscribed_tokens - set(token_ids)
        for token_id in old_tokens:
            if self._price_monitor:
                await self._price_monitor.unsubscribe_token(token_id)
            self._subscribed_tokens.discard(token_id)

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

    async def get_market_data(self, token_id: str, fallback_timeout: int = 10) -> Optional[MarketData]:
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
                        yes_price=price_update.yes_price,
                        no_price=price_update.no_price,
                        change_24h=0,
                        volume=price_update.volume or 0,
                        hours_to_expiry=0,
                        timestamp=price_update.timestamp or datetime.utcnow()
                    )
                # else: WebSocket 数据太旧，用 HTTP fallback

        # 2. HTTP fallback (WebSocket 无数据或超时)
        return await self._fetch_price_http(token_id)

    async def _fetch_price_http(self, token_id: str) -> Optional[MarketData]:
        """HTTP fallback 获取价格"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 获取 token 信息
                url = f"https://clob.polymarket.com/markets/{token_id}"
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    return MarketData(
                        market_id=token_id,
                        token_id=token_id,
                        yes_price=data.get('yes_price', 0.5),
                        no_price=data.get('no_price', 0.5),
                        change_24h=data.get('change24h', 0),
                        volume=data.get('volume', 0),
                        hours_to_expiry=0,
                        timestamp=datetime.utcnow()
                    )
        except Exception as e:
            print(f"HTTP fallback failed for {token_id}: {e}")

        return None

    async def get_activity(self, token_id: str) -> Optional[ActivityData]:
        """Get activity data from analyzer cache."""
        if not self._activity_analyzer:
            return None

        # Look up condition_id from token_id mapping
        condition_id = self._token_to_condition.get(token_id, token_id)

        # Get MarketActivity from ActivityAnalyzer cache
        ma = self._activity_analyzer.get_market_by_condition(condition_id)
        if ma:
            return ActivityData(
                market_id=condition_id,
                netflow=ma.net_flow,
                buy_volume=ma.yes_volume,
                sell_volume=ma.no_volume,
                unique_traders=ma.trader_count,
                timestamp=datetime.utcnow()
            )

        # Fallback: empty data
        return ActivityData(
            market_id=condition_id,
            netflow=0,
            buy_volume=0,
            sell_volume=0,
            unique_traders=0,
            timestamp=datetime.utcnow()
        )

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
        self.max_hours_to_expiry = filters.get('max_hours_to_expiry', 6)

    def filter_market(self, market_data: MarketData) -> bool:
        """
        过滤市场数据，返回 True 表示通过过滤
        """
        # 1. 价格区间过滤
        price = market_data.yes_price
        if not (self.min_price <= price <= self.max_price):
            return False

        # 2. 死亡区间过滤
        if self.dead_zone_enabled:
            if self.dead_zone_min <= price <= self.dead_zone_max:
                return False  # 在死亡区间内，不交易

        # 3. 到期时间过滤
        if self.max_hours_to_expiry > 0:
            if market_data.hours_to_expiry > self.max_hours_to_expiry:
                return False  # 超过最大到期时间

        return True

    def filter_by_keywords(self, market_name: str) -> bool:
        """关键词过滤"""
        for keyword in self.keywords_exclude:
            if keyword.lower() in market_name.lower():
                return False
        return True


class TriggerChecker:
    """Trigger condition checker using StrategyTrigger configuration"""

    # 分层净流入阈值（来自 polymarket-agent）
    # 注意：Stage 阈值必须避开死亡区间 (0.60-0.85)
    STAGE_THRESHOLDS = [
        {'min_price': 0.95, 'max_price': 0.999, 'netflow': 2000},   # Stage1: 高概率
        {'min_price': 0.90, 'max_price': 0.95, 'netflow': 1000},    # Stage2
        {'min_price': 0.85, 'max_price': 0.90, 'netflow': 10000},   # Stage3: min 改为 0.85 避开死亡区间
        # Stage4 (0.70-0.80) 已删除 - 完全在死亡区间内，死代码
    ]

    def __init__(self, trigger: Dict[str, Any], last_trigger_time: Optional[datetime] = None):
        self.price_change_threshold = trigger.get('price_change_threshold', 5)  # 5%
        self.min_trigger_interval = trigger.get('min_trigger_interval', 5)  # 5 分钟
        self.use_stage_netflow = trigger.get('use_stage_netflow', True)  # 使用分层阈值

        # 基础净流入阈值（当不使用分层时）
        self.base_netflow_threshold = trigger.get('activity_netflow_threshold', 1000)

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
                source_class = _DATA_SOURCE_REGISTRY.get(source_type)
                if not source_class:
                    raise ValueError(f"Unknown data source type: {source_type}")

                source = source_class(**kwargs)
                await source.start()
                self._sources[portfolio_id] = source

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
        for source in self._sources.values():
            await source.stop()
        self._sources.clear()
        self._filters.clear()
        self._triggers.clear()


# Global singleton
_data_source_manager: Optional[DataSourceManager] = None


def get_data_source_manager() -> DataSourceManager:
    """Get data source manager singleton"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager