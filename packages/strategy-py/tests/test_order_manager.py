"""
Tests for the OrderManager class.
"""

import asyncio
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from polymarket.order_manager import (
    OrderManager,
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
    get_order_manager,
    reset_order_manager
)


class TestOrder:
    """Tests for Order dataclass."""

    def test_order_creation(self):
        """Test basic order creation."""
        order = Order(
            id="test-123",
            market_id="market-456",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        assert order.id == "test-123"
        assert order.market_id == "market-456"
        assert order.side == OrderSide.BUY
        assert order.size == 100.0
        assert order.price == 0.5
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.PENDING
        assert order.remaining_size == 100.0

    def test_order_to_dict(self):
        """Test order serialization to dict."""
        order = Order(
            id="test-123",
            market_id="market-456",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            filled_size=100.0,
            remaining_size=0.0
        )

        data = order.to_dict()

        assert data["id"] == "test-123"
        assert data["side"] == "buy"
        assert data["status"] == "filled"
        assert data["filled_size"] == 100.0

    def test_order_from_dict(self):
        """Test order deserialization from dict."""
        data = {
            "id": "test-123",
            "market_id": "market-456",
            "side": "sell",
            "size": 50.0,
            "price": 0.75,
            "order_type": "market",
            "status": "open",
            "filled_size": 0.0,
            "remaining_size": 50.0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "cancelled_at": None,
            "filled_at": None,
            "reject_reason": None,
            "metadata": "{}"
        }

        order = Order.from_dict(data)

        assert order.id == "test-123"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.OPEN


class TestOrderManager:
    """Tests for OrderManager class."""

    @pytest.fixture
    async def order_manager(self):
        """Create a temporary OrderManager for testing."""
        reset_order_manager()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        manager = OrderManager(db_path=db_path)
        yield manager

        # Cleanup
        manager.close()
        reset_order_manager()
        Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_create_order(self, order_manager):
        """Test creating a new order."""
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        assert order.id.startswith("ord_")
        assert order.market_id == "market-123"
        assert order.side == OrderSide.BUY
        assert order.size == 100.0
        assert order.price == 0.5
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.PENDING
        assert order.remaining_size == 100.0

    @pytest.mark.asyncio
    async def test_create_order_validation(self, order_manager):
        """Test order creation validation."""
        # Invalid size
        with pytest.raises(ValueError, match="size must be positive"):
            await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=0,
                price=0.5,
                order_type=OrderType.LIMIT
            )

        # Invalid price
        with pytest.raises(ValueError, match="price must be positive"):
            await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=100.0,
                price=-1,
                order_type=OrderType.LIMIT
            )

        # Empty market_id
        with pytest.raises(ValueError, match="Market ID cannot be empty"):
            await order_manager.create_order(
                market_id="",
                side=OrderSide.BUY,
                size=100.0,
                price=0.5,
                order_type=OrderType.LIMIT
            )

    @pytest.mark.asyncio
    async def test_get_order(self, order_manager):
        """Test getting an order by ID."""
        # Create an order
        created = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Get the order
        fetched = await order_manager.get_order(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.market_id == created.market_id
        assert fetched.size == created.size

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, order_manager):
        """Test getting a non-existent order."""
        order = await order_manager.get_order("non-existent-id")
        assert order is None

    @pytest.mark.asyncio
    async def test_list_orders(self, order_manager):
        """Test listing orders."""
        # Create multiple orders
        for i in range(5):
            await order_manager.create_order(
                market_id=f"market-{i % 2}",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                size=100.0 + i,
                price=0.5,
                order_type=OrderType.LIMIT
            )

        # List all orders
        all_orders = await order_manager.list_orders()
        assert len(all_orders) == 5

        # List with status filter
        pending_orders = await order_manager.list_orders(status=OrderStatus.PENDING)
        assert len(pending_orders) == 5

        # List with market filter
        market_orders = await order_manager.list_orders(market_id="market-0")
        assert len(market_orders) == 3  # orders 0, 2, 4

    @pytest.mark.asyncio
    async def test_cancel_order(self, order_manager):
        """Test cancelling an order."""
        # Create an order
        created = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Cancel the order
        cancelled = await order_manager.cancel_order(created.id)

        assert cancelled.status == OrderStatus.CANCELLED
        assert cancelled.cancelled_at is not None
        assert cancelled.id == created.id

        # Verify order is not in active orders
        active = await order_manager.get_active_orders_from_cache()
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, order_manager):
        """Test cancelling a non-existent order."""
        with pytest.raises(ValueError, match="Order not found"):
            await order_manager.cancel_order("non-existent-id")

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager):
        """Test cancelling all orders."""
        # Create multiple orders
        for i in range(5):
            await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=100.0,
                price=0.5,
                order_type=OrderType.LIMIT
            )

        # Cancel all orders
        cancelled = await order_manager.cancel_all_orders()

        assert len(cancelled) == 5
        for order in cancelled:
            assert order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_update_order_status(self, order_manager):
        """Test updating order status."""
        # Create an order
        created = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Update to open
        updated = await order_manager.update_order_status(
            created.id,
            OrderStatus.OPEN
        )
        assert updated.status == OrderStatus.OPEN

        # Update to partially filled
        updated = await order_manager.update_order_status(
            created.id,
            OrderStatus.PARTIALLY_FILLED,
            filled_size=50.0
        )
        assert updated.status == OrderStatus.PARTIALLY_FILLED
        assert updated.filled_size == 50.0
        assert updated.remaining_size == 50.0

        # Update to filled
        updated = await order_manager.update_order_status(
            created.id,
            OrderStatus.FILLED,
            filled_size=100.0
        )
        assert updated.status == OrderStatus.FILLED
        assert updated.filled_size == 100.0
        assert updated.remaining_size == 0.0
        assert updated.filled_at is not None

    @pytest.mark.asyncio
    async def test_status_callback(self, order_manager):
        """Test status change callbacks."""
        callbacks_received = []

        def callback(order, new_status):
            callbacks_received.append((order.id, new_status))

        order_manager.add_status_callback(callback)

        # Create order (no callback for initial status)
        created = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Update status (should trigger callback)
        await order_manager.update_order_status(created.id, OrderStatus.OPEN)

        assert len(callbacks_received) == 1
        assert callbacks_received[0][0] == created.id
        assert callbacks_received[0][1] == OrderStatus.OPEN

        # Remove callback
        order_manager.remove_status_callback(callback)

        # Another update should not trigger callback
        await order_manager.update_order_status(created.id, OrderStatus.FILLED)
        assert len(callbacks_received) == 1  # Still 1

    @pytest.mark.asyncio
    async def test_get_order_stats(self, order_manager):
        """Test order statistics."""
        # Create orders with different statuses
        for i in range(3):
            order = await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=100.0,
                price=0.5,
                order_type=OrderType.LIMIT
            )
            if i == 0:
                await order_manager.update_order_status(order.id, OrderStatus.FILLED, filled_size=100.0)
            elif i == 1:
                await order_manager.cancel_order(order.id)

        # Also add order to different market
        await order_manager.create_order(
            market_id="market-456",
            side=OrderSide.SELL,
            size=50.0,
            price=0.6,
            order_type=OrderType.LIMIT
        )

        # Get stats for all markets
        stats = await order_manager.get_order_stats()

        assert stats["total_orders"] == 4
        assert stats["status_breakdown"]["filled"] == 1
        assert stats["status_breakdown"]["cancelled"] == 1
        assert stats["status_breakdown"]["pending"] == 2
        assert stats["active_orders"] == 2
        assert stats["filled_statistics"]["total_filled_size"] == 100.0

        # Get stats for specific market
        stats = await order_manager.get_order_stats(market_id="market-123")
        assert stats["total_orders"] == 3

    @pytest.mark.asyncio
    async def test_persistence(self, order_manager):
        """Test that orders are persisted to database."""
        # Create order
        created = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT,
            metadata={"strategy": "test"}
        )

        # Create new manager instance with same database
        db_path = order_manager.db_path
        new_manager = OrderManager(db_path=db_path)

        try:
            # Order should be retrievable
            fetched = await new_manager.get_order(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.market_id == created.market_id
            assert fetched.metadata == {"strategy": "test"}
        finally:
            new_manager.close()

    @pytest.mark.asyncio
    async def test_get_order_history(self, order_manager):
        """Test getting order history."""
        # Create and fill some orders
        for i in range(3):
            order = await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=100.0,
                price=0.5,
                order_type=OrderType.LIMIT
            )
            await order_manager.update_order_status(order.id, OrderStatus.FILLED, filled_size=100.0)

        # Create one cancelled order
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.SELL,
            size=50.0,
            price=0.6,
            order_type=OrderType.LIMIT
        )
        await order_manager.cancel_order(order.id)

        # Get history
        history = await order_manager.get_order_history()

        assert len(history) == 4

        # All should be terminal states
        for order in history:
            assert order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async with OrderManager(db_path=db_path) as manager:
                order = await manager.create_order(
                    market_id="market-123",
                    side=OrderSide.BUY,
                    size=100.0,
                    price=0.5,
                    order_type=OrderType.LIMIT
                )
                assert order.id is not None

            # After exiting context, manager should be closed
            assert len(manager._active_orders) == 0
        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_string_enums(self, order_manager):
        """Test that string values work for enums."""
        order = await order_manager.create_order(
            market_id="market-123",
            side="buy",  # String instead of enum
            size=100.0,
            price=0.5,
            order_type="limit"  # String instead of enum
        )

        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_reject_order(self, order_manager):
        """Test rejecting an order."""
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        updated = await order_manager.update_order_status(
            order.id,
            OrderStatus.REJECTED,
            reject_reason="Insufficient funds"
        )

        assert updated.status == OrderStatus.REJECTED
        assert updated.reject_reason == "Insufficient funds"

    @pytest.mark.asyncio
    async def test_update_nonexistent_order(self, order_manager):
        """Test updating a non-existent order."""
        with pytest.raises(ValueError, match="Order not found"):
            await order_manager.update_order_status(
                "non-existent-id",
                OrderStatus.FILLED
            )

    @pytest.mark.asyncio
    async def test_cancel_non_cancellable_order(self, order_manager):
        """Test cancelling an already filled order."""
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Fill the order
        await order_manager.update_order_status(
            order.id,
            OrderStatus.FILLED,
            filled_size=100.0
        )

        # Try to cancel filled order
        result = await order_manager.cancel_order(order.id)
        # Should return the order without cancelling
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_list_orders_pagination(self, order_manager):
        """Test order listing with pagination."""
        # Create 10 orders
        for i in range(10):
            await order_manager.create_order(
                market_id="market-123",
                side=OrderSide.BUY,
                size=100.0,
                price=0.5,
                order_type=OrderType.LIMIT
            )

        # Test limit
        orders = await order_manager.list_orders(limit=5)
        assert len(orders) == 5

        # Test offset
        orders_page2 = await order_manager.list_orders(limit=5, offset=5)
        assert len(orders_page2) == 5

        # Verify different pages
        assert orders[0].id != orders_page2[0].id

    @pytest.mark.asyncio
    async def test_get_order_history_with_time_filter(self, order_manager):
        """Test getting order history with time filters."""
        # Create and fill an order
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )
        await order_manager.update_order_status(order.id, OrderStatus.FILLED, filled_size=100.0)

        # Get history with start time
        start_time = datetime.utcnow()
        history = await order_manager.get_order_history(start_time=start_time)
        assert len(history) == 0

        # Get history with end time
        end_time = datetime.utcnow()
        history = await order_manager.get_order_history(end_time=end_time)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_status_callback_with_multiple_callbacks(self, order_manager):
        """Test multiple status callbacks."""
        callbacks1 = []
        callbacks2 = []

        def callback1(order, new_status):
            callbacks1.append((order.id, new_status))

        def callback2(order, new_status):
            callbacks2.append((order.id, new_status))

        order_manager.add_status_callback(callback1)
        order_manager.add_status_callback(callback2)

        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        await order_manager.update_order_status(order.id, OrderStatus.OPEN)

        assert len(callbacks1) == 1
        assert len(callbacks2) == 1
        assert callbacks1[0][0] == order.id
        assert callbacks2[0][0] == order.id

    @pytest.mark.asyncio
    async def test_partial_fill(self, order_manager):
        """Test partial fill of an order."""
        order = await order_manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )

        # Partial fill
        updated = await order_manager.update_order_status(
            order.id,
            OrderStatus.PARTIALLY_FILLED,
            filled_size=30.0
        )

        assert updated.status == OrderStatus.PARTIALLY_FILLED
        assert updated.filled_size == 30.0
        assert updated.remaining_size == 70.0

        # Complete fill
        updated = await order_manager.update_order_status(
            order.id,
            OrderStatus.FILLED,
            filled_size=100.0
        )

        assert updated.status == OrderStatus.FILLED
        assert updated.filled_size == 100.0
        assert updated.remaining_size == 0.0
        assert updated.filled_at is not None


class TestOrderManagerSingleton:
    """Tests for OrderManager singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_order_manager()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_order_manager()

    def test_singleton_instance(self):
        """Test that get_order_manager returns same instance."""
        manager1 = get_order_manager()
        manager2 = get_order_manager()

        assert manager1 is manager2

    def test_reset_order_manager(self):
        """Test resetting the singleton."""
        manager1 = get_order_manager()
        reset_order_manager()
        manager2 = get_order_manager()

        assert manager1 is not manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])