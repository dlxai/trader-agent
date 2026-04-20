"""Data collector for market data."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from uuid import UUID

from .event_bus import EventBus, EventType, Event


@dataclass
class MarketData:
    """Market data snapshot."""
    market_id: str
    symbol: str
    timestamp: datetime

    # Price data
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    mid_price: Optional[Decimal] = None

    # Volume data
    volume_24h: Optional[Decimal] = None
    volume_base: Optional[Decimal] = None

    # Change data
    change_24h: Optional[Decimal] = None
    change_percent_24h: Optional[Decimal] = None

    # Order book summary
    bid_depth: Optional[Decimal] = None
    ask_depth: Optional[Decimal] = None
    spread: Optional[Decimal] = None
    spread_percent: Optional[Decimal] = None

    # Metadata
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TradeUpdate:
    """Trade execution update."""
    trade_id: str
    market_id: str
    symbol: str
    timestamp: datetime

    side: str  # "buy" or "sell"
    size: Decimal
    price: Decimal

    buyer_order_id: Optional[str] = None
    seller_order_id: Optional[str] = None

    # For aggregated trades
    trade_count: int = 1
    first_trade_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None


@dataclass
class OrderBookUpdate:
    """Order book update."""
    market_id: str
    symbol: str
    timestamp: datetime

    bids: List[tuple]  # [(price, size), ...] sorted by price desc
    asks: List[tuple]  # [(price, size), ...] sorted by price asc

    # Optional depth statistics
    bid_depth_total: Optional[Decimal] = None
    ask_depth_total: Optional[Decimal] = None
    bid_levels: Optional[int] = None
    ask_levels: Optional[int] = None


class DataSource(ABC):
    """Abstract base class for data sources."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.is_connected = False
        self._callbacks: List[Callable] = []

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the data source."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the data source."""
        pass

    @abstractmethod
    async def subscribe(self, market_id: str) -> None:
        """Subscribe to market data."""
        pass

    @abstractmethod
    async def unsubscribe(self, market_id: str) -> None:
        """Unsubscribe from market data."""
        pass

    def register_callback(self, callback: Callable) -> None:
        """Register a callback for data updates."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _notify_callbacks(self, data: Any) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                print(f"Error in callback: {e}")


class DataCollector:
    """Main data collector that manages multiple data sources."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._sources: Dict[str, DataSource] = {}
        self._market_subscriptions: Dict[str, List[str]] = {}  # market_id -> [source_names]
        self._running = False

    def register_source(self, source: DataSource) -> None:
        """Register a data source."""
        self._sources[source.name] = source
        # Register callback for data updates
        source.register_callback(self._handle_data_update)

    def unregister_source(self, source_name: str) -> None:
        """Unregister a data source."""
        if source_name in self._sources:
            source = self._sources[source_name]
            source.unregister_callback(self._handle_data_update)
            del self._sources[source_name]

    async def start(self) -> None:
        """Start the data collector."""
        self._running = True
        for source in self._sources.values():
            if not source.is_connected:
                await source.connect()

    async def stop(self) -> None:
        """Stop the data collector."""
        self._running = False
        for source in self._sources.values():
            if source.is_connected:
                await source.disconnect()

    async def subscribe(self, market_id: str, source_name: Optional[str] = None) -> None:
        """Subscribe to market data."""
        if market_id not in self._market_subscriptions:
            self._market_subscriptions[market_id] = []

        if source_name:
            # Subscribe to specific source
            if source_name in self._sources:
                await self._sources[source_name].subscribe(market_id)
                self._market_subscriptions[market_id].append(source_name)
        else:
            # Subscribe to all sources
            for name, source in self._sources.items():
                await source.subscribe(market_id)
                self._market_subscriptions[market_id].append(name)

    async def unsubscribe(self, market_id: str, source_name: Optional[str] = None) -> None:
        """Unsubscribe from market data."""
        if market_id not in self._market_subscriptions:
            return

        if source_name:
            # Unsubscribe from specific source
            if source_name in self._sources:
                await self._sources[source_name].unsubscribe(market_id)
                if source_name in self._market_subscriptions[market_id]:
                    self._market_subscriptions[market_id].remove(source_name)
        else:
            # Unsubscribe from all sources
            for source_name in self._market_subscriptions[market_id]:
                if source_name in self._sources:
                    await self._sources[source_name].unsubscribe(market_id)
            self._market_subscriptions[market_id] = []

    async def _handle_data_update(self, data: Any) -> None:
        """Handle data updates from sources."""
        # Create event based on data type
        if isinstance(data, MarketData):
            event = self.event_bus.create_event(
                event_type=EventType.MARKET_DATA_UPDATE,
                source="data_collector",
                payload={
                    "market_id": data.market_id,
                    "symbol": data.symbol,
                    "bid": str(data.bid) if data.bid else None,
                    "ask": str(data.ask) if data.ask else None,
                    "last_price": str(data.last_price) if data.last_price else None,
                    "timestamp": data.timestamp.isoformat(),
                },
            )
            await self.event_bus.publish(EventType.MARKET_DATA_UPDATE, event)

        elif isinstance(data, TradeUpdate):
            event = self.event_bus.create_event(
                event_type=EventType.TRADE_UPDATE,
                source="data_collector",
                payload={
                    "trade_id": data.trade_id,
                    "market_id": data.market_id,
                    "symbol": data.symbol,
                    "side": data.side,
                    "size": str(data.size),
                    "price": str(data.price),
                    "timestamp": data.timestamp.isoformat(),
                },
            )
            await self.event_bus.publish(EventType.TRADE_UPDATE, event)

        elif isinstance(data, OrderBookUpdate):
            event = self.event_bus.create_event(
                event_type=EventType.ORDER_BOOK_UPDATE,
                source="data_collector",
                payload={
                    "market_id": data.market_id,
                    "symbol": data.symbol,
                    "bids": data.bids[:10],  # Top 10 bids
                    "asks": data.asks[:10],  # Top 10 asks
                    "timestamp": data.timestamp.isoformat(),
                },
            )
            await self.event_bus.publish(EventType.ORDER_BOOK_UPDATE, event)


# Convenience function to create a data collector
def create_data_collector(event_bus: EventBus) -> DataCollector:
    """Create and configure a data collector."""
    return DataCollector(event_bus)
