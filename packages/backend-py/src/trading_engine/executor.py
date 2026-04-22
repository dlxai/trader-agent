"""Order executor for trading engine."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from .event_bus import EventBus, EventType, Event


class ExecutionStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class ExecutionResult:
    """Result of order execution."""
    success: bool
    order_id: str
    status: ExecutionStatus
    filled_size: Decimal
    avg_fill_price: Decimal
    total_cost: Decimal
    fees: Decimal
    slippage: Decimal
    execution_time_ms: int
    error_message: Optional[str] = None
    exchange_order_id: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class ExchangeAdapter(ABC):
    """Abstract adapter for exchange connections."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.is_connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Connect to exchange."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        pass

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Submit order to exchange."""
        pass

    @abstractmethod
    async def cancel_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> bool:
        """Cancel order on exchange."""
        pass

    @abstractmethod
    async def get_order_status(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> Dict[str, Any]:
        """Get order status from exchange."""
        pass


class MockExchangeAdapter(ExchangeAdapter):
    """Mock exchange adapter for testing."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("mock", config)
        self.orders: Dict[str, Dict[str, Any]] = {}
        self._order_counter = 0

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
    ) -> ExecutionResult:
        self._order_counter += 1
        exchange_order_id = f"MOCK_{self._order_counter}"

        # Simulate fill
        fill_price = price or Decimal("0.5")  # Default mock price
        fill_time = 10  # 10ms mock execution

        result = ExecutionResult(
            success=True,
            order_id=client_order_id or str(uuid4()),
            status=ExecutionStatus.FILLED,
            filled_size=size,
            avg_fill_price=fill_price,
            total_cost=fill_price * size,
            fees=Decimal("0"),
            slippage=Decimal("0"),
            execution_time_ms=fill_time,
            exchange_order_id=exchange_order_id,
        )

        # Store order
        self.orders[exchange_order_id] = {
            "id": exchange_order_id,
            "symbol": symbol,
            "side": side,
            "status": "filled",
            "filled_size": str(size),
            "avg_price": str(fill_price),
        }

        return result

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        if exchange_order_id in self.orders:
            self.orders[exchange_order_id]["status"] = "cancelled"
            return True
        return False

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> Dict[str, Any]:
        return self.orders.get(exchange_order_id, {})


class OrderExecutor:
    """Order executor that manages order execution."""

    def __init__(
        self,
        event_bus: EventBus,
        exchange_adapter: Optional[ExchangeAdapter] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.event_bus = event_bus
        self.exchange_adapter = exchange_adapter or MockExchangeAdapter({})
        self.config = config or {}
        self._unsubscribe = None
        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        """Start the executor."""
        await self.exchange_adapter.connect()
        self._running = True
        self._unsubscribe = self.event_bus.subscribe(
            EventType.SIGNAL_APPROVED,
            self._handle_approved_signal,
        )
        # Start execution loop
        asyncio.create_task(self._execution_loop())

    async def stop(self) -> None:
        """Stop the executor."""
        self._running = False
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        await self.exchange_adapter.disconnect()

    async def _execution_loop(self) -> None:
        """Main execution loop."""
        while self._running:
            try:
                order_data = await asyncio.wait_for(
                    self._execution_queue.get(),
                    timeout=1.0,
                )
                await self._execute_order(order_data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error in execution loop: {e}")

    async def _handle_approved_signal(self, event: Event) -> None:
        """Handle approved signal events."""
        signal_data = event.payload

        # Convert to order data
        order_data = self._signal_to_order(signal_data)

        # Queue for execution
        await self._execution_queue.put(order_data)

        # Publish order created event
        order_event = self.event_bus.create_event(
            event_type=EventType.ORDER_CREATED,
            source="executor",
            payload=order_data,
        )
        await self.event_bus.publish(order_event)

    def _signal_to_order(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert signal to order data."""
        return {
            "order_id": str(uuid4()),
            "symbol": signal_data["symbol"],
            "side": signal_data["side"],
            "order_type": signal_data.get("order_type", "market"),
            "size": Decimal(str(signal_data["suggested_size"])),
            "price": Decimal(str(signal_data.get("suggested_entry", "0"))),
            "stop_price": None,
            "time_in_force": signal_data.get("time_in_force", "GTC"),
            "signal_id": signal_data["signal_id"],
        }

    async def _execute_order(self, order_data: Dict[str, Any]) -> None:
        """Execute an order."""
        # Publish order submitted event
        submit_event = self.event_bus.create_event(
            event_type=EventType.ORDER_SUBMITTED,
            source="executor",
            payload=order_data,
        )
        await self.event_bus.publish(submit_event)

        # Execute via exchange adapter
        result = await self.exchange_adapter.submit_order(
            symbol=order_data["symbol"],
            side=order_data["side"],
            order_type=order_data["order_type"],
            size=order_data["size"],
            price=order_data.get("price"),
            stop_price=order_data.get("stop_price"),
            time_in_force=order_data["time_in_force"],
            client_order_id=order_data["order_id"],
        )

        # Publish result event
        if result.status in [ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED]:
            event_type = EventType.ORDER_FILLED if result.status == ExecutionStatus.FILLED else EventType.ORDER_PARTIALLY_FILLED
        elif result.status == ExecutionStatus.REJECTED:
            event_type = EventType.ORDER_REJECTED
        else:
            event_type = EventType.ORDER_CANCELLED

        result_event = self.event_bus.create_event(
            event_type=event_type,
            source="executor",
            payload={
                "order_id": order_data["order_id"],
                "signal_id": order_data["signal_id"],
                "exchange_order_id": result.exchange_order_id,
                "status": result.status.value,
                "filled_size": str(result.filled_size),
                "avg_fill_price": str(result.avg_fill_price),
                "total_cost": str(result.total_cost),
                "fees": str(result.fees),
                "slippage": str(result.slippage),
                "execution_time_ms": result.execution_time_ms,
                "error_message": result.error_message,
            },
        )
        result_event.type = event_type
        await self.event_bus.publish(result_event)


def create_executor(
    event_bus: EventBus,
    exchange_adapter: Optional[ExchangeAdapter] = None,
    config: Optional[Dict[str, Any]] = None,
) -> OrderExecutor:
    """Create and configure an order executor."""
    return OrderExecutor(event_bus, exchange_adapter, config)
