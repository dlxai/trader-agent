"""WebSocket Sources - Global singleton connections."""

import asyncio
from typing import Optional


class ActivityWebSocketSource:
    """Activity WebSocket - Global singleton.

    Receives capital flow data from Polymarket.
    Publishes to EventBus.
    """
    _instance: Optional["ActivityWebSocketSource"] = None
    _lock: asyncio.Lock = None

    def __init__(self):
        self.event_bus = None
        self._running = False
        self._ws = None
        if ActivityWebSocketSource._lock is None:
            ActivityWebSocketSource._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "ActivityWebSocketSource":
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def connect(self) -> None:
        """Connect to Activity WebSocket."""
        self._running = True

    async def disconnect(self) -> None:
        """Disconnect from Activity WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()

    def set_event_bus(self, event_bus) -> None:
        """Set EventBus for publishing."""
        self.event_bus = event_bus


class SportsWebSocketSource:
    """Sports WebSocket - Global singleton.

    Receives sports score updates.
    Publishes to EventBus.
    """
    _instance: Optional["SportsWebSocketSource"] = None
    _lock: asyncio.Lock = None

    def __init__(self):
        self.event_bus = None
        self._running = False
        self._ws = None
        if SportsWebSocketSource._lock is None:
            SportsWebSocketSource._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "SportsWebSocketSource":
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def connect(self) -> None:
        """Connect to Sports WebSocket."""
        self._running = True

    async def disconnect(self) -> None:
        """Disconnect from Sports WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()

    def set_event_bus(self, event_bus) -> None:
        """Set EventBus for publishing."""
        self.event_bus = event_bus
