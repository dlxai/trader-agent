"""Data source manager for shared WebSocket connections."""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MarketData:
    """Market data"""
    market_id: str
    price: float
    change_24h: float
    volume: float
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
    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """Get market data"""
        pass

    @abstractmethod
    async def get_activity(self, market_id: str) -> Optional[ActivityData]:
        """Get activity data"""
        pass

    @abstractmethod
    async def get_sports_score(self, market_id: str) -> Optional[SportsScoreData]:
        """Get sports score"""
        pass


class PolymarketDataSource(DataSource):
    """Polymarket data source implementation"""

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        self._proxy_url = proxy_url
        self._running = False
        self._market_cache: Dict[str, MarketData] = {}
        self._activity_cache: Dict[str, ActivityData] = {}
        self._sports_cache: Dict[str, SportsScoreData] = {}
        self._ws_task: Optional[asyncio.Task] = None

    @property
    def source_type(self) -> str:
        return "polymarket"

    async def start(self) -> None:
        """Start WebSocket connection"""
        self._running = True
        # WebSocket connection will be implemented here
        # For now, just set the flag

    async def stop(self) -> None:
        """Stop data source"""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        return self._market_cache.get(market_id)

    async def get_activity(self, market_id: str) -> Optional[ActivityData]:
        return self._activity_cache.get(market_id)

    async def get_sports_score(self, market_id: str) -> Optional[SportsScoreData]:
        return self._sports_cache.get(market_id)


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

    async def get_or_create_source(
        self,
        portfolio_id: UUID,
        source_type: str = "polymarket",
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

            return self._sources[portfolio_id]

    async def remove_source(self, portfolio_id: UUID) -> None:
        """Remove data source"""
        async with self._lock:
            if portfolio_id in self._sources:
                await self._sources[portfolio_id].stop()
                del self._sources[portfolio_id]

    async def get_all_sources(self) -> List[DataSource]:
        """Get all data sources"""
        return list(self._sources.values())

    async def close_all(self) -> None:
        """Close all data sources"""
        for source in self._sources.values():
            await source.stop()
        self._sources.clear()


# Global singleton
_data_source_manager: Optional[DataSourceManager] = None


def get_data_source_manager() -> DataSourceManager:
    """Get data source manager singleton"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager