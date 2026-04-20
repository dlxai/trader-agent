"""Event bus for trading engine."""

from enum import Enum, auto
from typing import Callable, Dict, List, TypeVar, Any
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

T = TypeVar("T")


class EventType(Enum):
    """Event types for the trading engine."""

    # Market data events
    MARKET_DATA_UPDATE = auto()
    PRICE_TICK = auto()
    ORDER_BOOK_UPDATE = auto()
    TRADE_UPDATE = auto()

    # Signal events
    SIGNAL_GENERATED = auto()
    SIGNAL_ANALYZED = auto()
    SIGNAL_APPROVED = auto()
    SIGNAL_REJECTED = auto()

    # Order events
    ORDER_CREATED = auto()
    ORDER_SUBMITTED = auto()
    ORDER_FILLED = auto()
    ORDER_PARTIALLY_FILLED = auto()
    ORDER_CANCELLED = auto()
    ORDER_REJECTED = auto()
    ORDER_EXPIRED = auto()

    # Position events
    POSITION_OPENED = auto()
    POSITION_UPDATED = auto()
    POSITION_CLOSED = auto()
    POSITION_LIQUIDATED = auto()

    # Risk events
    RISK_LIMIT_EXCEEDED = auto()
    DAILY_LOSS_LIMIT_HIT = auto()
    WEEKLY_LOSS_LIMIT_HIT = auto()
    KILL_SWITCH_TRIGGERED = auto()

    # System events
    ENGINE_STARTED = auto()
    ENGINE_STOPPED = auto()
    ERROR_OCCURRED = auto()


@dataclass
class Event:
    """Base event class."""

    type: EventType
    timestamp: datetime
    source: str
    payload: Dict[str, Any]
    correlation_id: str = ""
    user_id: UUID = None

    def __post_init__(self):
        if not self.correlation_id:
            from uuid import uuid4
            self.correlation_id = str(uuid4())


class EventBus:
    """Event bus for publish/subscribe pattern."""

    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._global_handlers: List[Callable] = []

    def subscribe(
        self, event_type: EventType, handler: Callable[[Event], None]
    ) -> Callable:
        """Subscribe to a specific event type.

        Returns an unsubscribe function.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)

        # Return unsubscribe function
        def unsubscribe():
            if event_type in self._handlers and handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

        return unsubscribe

    def subscribe_all(self, handler: Callable[[Event], None]) -> Callable:
        """Subscribe to all events.

        Returns an unsubscribe function.
        """
        self._global_handlers.append(handler)

        def unsubscribe():
            if handler in self._global_handlers:
                self._global_handlers.remove(handler)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        import asyncio

        # Call global handlers
        for handler in self._global_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                # Log error but don't stop other handlers
                print(f"Error in global handler: {e}")

        # Call type-specific handlers
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    # Log error but don't stop other handlers
                    print(f"Error in handler for {event.type}: {e}")

    def create_event(
        self,
        event_type: EventType,
        source: str,
        payload: Dict[str, Any],
        user_id: UUID = None,
    ) -> Event:
        """Create an event with current timestamp."""
        return Event(
            type=event_type,
            timestamp=datetime.utcnow(),
            source=source,
            payload=payload,
            user_id=user_id,
        )
