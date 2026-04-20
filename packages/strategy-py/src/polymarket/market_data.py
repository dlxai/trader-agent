"""
市场数据管理模块 (Market Data Manager)
获取 Polymarket 市场信息、订单簿、价格历史等数据
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import aiohttp


logger = logging.getLogger(__name__)


class MarketStatus(Enum):
    """市场状态"""
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"
    PAUSED = "paused"


@dataclass
class Market:
    """市场信息"""
    id: str
    condition_id: str
    question: str
    description: str
    category: str
    status: MarketStatus
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    outcome_prices: Dict[str, float] = field(default_factory=dict)
    volume: float = 0.0
    liquidity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderBookLevel:
    """订单簿档位"""
    price: float
    size: float
    side: str  # "BID" 或 "ASK"


@dataclass
class OrderBook:
    """订单簿"""
    token_id: str
    market_id: str
    bids: List[OrderBookLevel]  # 买单（从高到低）
    asks: List[OrderBookLevel]  # 卖单（从低到高）
    timestamp: datetime
    spread: float = 0.0
    mid_price: float = 0.0

    def __post_init__(self):
        """计算 spread 和 mid price"""
        if self.bids and self.asks:
            best_bid = self.bids[0].price
            best_ask = self.asks[0].price
            self.spread = best_ask - best_bid
            self.mid_price = (best_bid + best_ask) / 2


@dataclass
class PriceHistoryPoint:
    """价格历史点"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PriceHistory:
    """价格历史"""
    token_id: str
    interval: str  # "1m", "5m", "15m", "1h", "1d"
    points: List[PriceHistoryPoint]
    start_time: datetime
    end_time: datetime


class MarketDataManager:
    """
    市场数据管理器

    负责获取和管理 Polymarket 的市场数据，包括：
    1. 市场列表获取
    2. 订单簿数据
    3. 价格历史
    4. 市场状态监控

    特性：
    - 数据缓存机制
    - 自动刷新
    - 批量查询优化
    """

    def __init__(
        self,
        api_client: Any,  # PolymarketClient 实例
        cache_duration_sec: int = 60,
        auto_refresh: bool = True,
    ):
        """
        初始化市场数据管理器

        Args:
            api_client: Polymarket API 客户端
            cache_duration_sec: 缓存有效期（秒）
            auto_refresh: 是否自动刷新数据
        """
        self.api_client = api_client
        self.cache_duration_sec = cache_duration_sec
        self.auto_refresh = auto_refresh

        # 数据缓存
        self._markets_cache: Dict[str, Market] = {}
        self._orderbooks_cache: Dict[str, OrderBook] = {}
        self._price_history_cache: Dict[str, PriceHistory] = {}

        # 缓存时间戳
        self._markets_cache_time: Optional[datetime] = None
        self._orderbooks_cache_time: Dict[str, datetime] = {}

        # 统计
        self._api_calls = 0
        self._cache_hits = 0
        self._errors = 0

        logger.info(
            f"MarketDataManager initialized (cache_duration={cache_duration_sec}s, "
            f"auto_refresh={auto_refresh})"
        )

    # ==================== 市场列表管理 ====================

    async def get_markets(
        self,
        status: Optional[MarketStatus] = None,
        category: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Market]:
        """
        获取市场列表

        Args:
            status: 按状态筛选
            category: 按类别筛选
            force_refresh: 强制刷新缓存

        Returns:
            市场列表
        """
        # 检查缓存
        if not force_refresh and self._is_markets_cache_valid():
            self._cache_hits += 1
            markets = list(self._markets_cache.values())
            logger.debug(f"Returning {len(markets)} markets from cache")
            return self._filter_markets(markets, status, category)

        # 从 API 获取
        try:
            self._api_calls += 1
            logger.info("Fetching markets from API...")

            # 调用 API（这里需要根据实际情况实现）
            # markets_data = await self.api_client.get_markets()
            markets_data = []  # 占位符

            # 解析并缓存
            self._markets_cache = {}
            for market_data in markets_data:
                market = self._parse_market(market_data)
                self._markets_cache[market.id] = market

            self._markets_cache_time = datetime.now()

            logger.info(f"Fetched and cached {len(self._markets_cache)} markets")

            return self._filter_markets(
                list(self._markets_cache.values()),
                status,
                category,
            )

        except Exception as e:
            self._errors += 1
            logger.error(f"Failed to fetch markets: {e}")

            # 如果有缓存，返回缓存数据
            if self._markets_cache:
                logger.warning("Returning stale markets from cache due to error")
                return self._filter_markets(
                    list(self._markets_cache.values()),
                    status,
                    category,
                )

            raise

    def _is_markets_cache_valid(self) -> bool:
        """检查市场缓存是否有效"""
        if not self._markets_cache_time:
            return False

        elapsed = (datetime.now() - self._markets_cache_time).total_seconds()
        return elapsed < self.cache_duration_sec

    def _filter_markets(
        self,
        markets: List[Market],
        status: Optional[MarketStatus],
        category: Optional[str],
    ) -> List[Market]:
        """筛选市场"""
        filtered = markets

        if status:
            filtered = [m for m in filtered if m.status == status]

        if category:
            filtered = [m for m in filtered if m.category == category]

        return filtered

    def _parse_market(self, data: Dict) -> Market:
        """解析市场数据"""
        return Market(
            id=data.get("id", ""),
            condition_id=data.get("condition_id", ""),
            question=data.get("question", ""),
            description=data.get("description", ""),
            category=data.get("category", ""),
            status=MarketStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            expires_at=datetime.fromisoformat(data.get("expires_at")) if data.get("expires_at") else None,
            resolved_at=datetime.fromisoformat(data.get("resolved_at")) if data.get("resolved_at") else None,
            outcome_prices=data.get("outcome_prices", {}),
            volume=data.get("volume", 0.0),
            liquidity=data.get("liquidity", 0.0),
            metadata=data.get("metadata", {}),
        )

    # ==================== 订单簿管理 ====================

    async def get_order_book(
        self,
        token_id: str,
        force_refresh: bool = False,
    ) -> OrderBook:
        """
        获取订单簿

        Args:
            token_id: Token ID
            force_refresh: 强制刷新

        Returns:
            订单簿
        """
        # 检查缓存
        if not force_refresh:
            cached = self._orderbooks_cache.get(token_id)
            cache_time = self._orderbooks_cache_time.get(token_id)

            if cached and cache_time:
                elapsed = (datetime.now() - cache_time).total_seconds()
                if elapsed < self.cache_duration_sec:
                    self._cache_hits += 1
                    logger.debug(f"Returning order book for {token_id} from cache")
                    return cached

        # 从 API 获取
        try:
            self._api_calls += 1
            logger.debug(f"Fetching order book for {token_id}...")

            # 调用 API（这里需要根据实际情况实现）
            # order_book_data = await self.api_client.get_order_book(token_id)
            order_book_data = {
                "token_id": token_id,
                "bids": [{"price": 0.55, "size": 100.0}, {"price": 0.54, "size": 200.0}],
                "asks": [{"price": 0.56, "size": 150.0}, {"price": 0.57, "size": 100.0}],
            }  # 占位符

            # 解析并缓存
            order_book = self._parse_order_book(order_book_data)
            self._orderbooks_cache[token_id] = order_book
            self._orderbooks_cache_time[token_id] = datetime.now()

            return order_book

        except Exception as e:
            self._errors += 1
            logger.error(f"Failed to fetch order book for {token_id}: {e}")

            # 如果有缓存，返回缓存数据
            if token_id in self._orderbooks_cache:
                logger.warning(f"Returning stale order book for {token_id} due to error")
                return self._orderbooks_cache[token_id]

            raise

    def _parse_order_book(self, data: Dict) -> OrderBook:
        """解析订单簿数据"""
        bids = [
            OrderBookLevel(price=b["price"], size=b["size"], side="BID")
            for b in data.get("bids", [])
        ]
        asks = [
            OrderBookLevel(price=a["price"], size=a["size"], side="ASK")
            for a in data.get("asks", [])
        ]

        # 排序：买单从高到低，卖单从低到高
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderBook(
            token_id=data.get("token_id", ""),
            market_id=data.get("market_id", ""),
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
        )

    # ==================== 统计和监控 ====================

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "api_calls": self._api_calls,
            "cache_hits": self._cache_hits,
            "errors": self._errors,
            "markets_cached": len(self._markets_cache),
            "orderbooks_cached": len(self._orderbooks_cache),
            "cache_duration_sec": self.cache_duration_sec,
        }

    def clear_cache(self):
        """清除所有缓存"""
        self._markets_cache.clear()
        self._orderbooks_cache.clear()
        self._price_history_cache.clear()
        self._markets_cache_time = None
        self._orderbooks_cache_time.clear()
        logger.info("All caches cleared")
