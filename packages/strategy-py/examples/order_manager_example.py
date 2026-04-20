"""
Order Manager Example

Demonstrates the usage of the OrderManager class for managing
order lifecycle, tracking order status, and SQLite persistence.
"""

import asyncio
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


async def example_basic_usage():
    """Example: Basic order creation and management."""
    print("\n" + "=" * 60)
    print("Example: Basic Order Management")
    print("=" * 60)

    # Create order manager with temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = OrderManager(db_path=db_path)

        # 1. Create a limit buy order
        print("\n1. Creating limit buy order...")
        order1 = await manager.create_order(
            market_id="0x1234567890abcdef",
            side=OrderSide.BUY,
            size=100.0,
            price=0.55,
            order_type=OrderType.LIMIT,
            metadata={"strategy": "momentum", "confidence": 0.85}
        )
        print(f"   Created order: {order1.id}")
        print(f"   Market: {order1.market_id}")
        print(f"   Side: {order1.side.value}")
        print(f"   Size: {order1.size}")
        print(f"   Price: {order1.price}")
        print(f"   Status: {order1.status.value}")

        # 2. Create a market sell order
        print("\n2. Creating market sell order...")
        order2 = await manager.create_order(
            market_id="0x1234567890abcdef",
            side=OrderSide.SELL,
            size=50.0,
            price=0.0,  # Market orders don't have a price
            order_type=OrderType.MARKET
        )
        print(f"   Created order: {order2.id}")

        # 3. List all orders
        print("\n3. Listing all orders...")
        all_orders = await manager.list_orders()
        print(f"   Total orders: {len(all_orders)}")
        for order in all_orders:
            print(f"   - {order.id}: {order.side.value} {order.size} @ {order.price} ({order.status.value})")

        # 4. Get a specific order
        print("\n4. Getting specific order...")
        fetched = await manager.get_order(order1.id)
        if fetched:
            print(f"   Found order: {fetched.id}")
            print(f"   Created at: {fetched.created_at}")
            print(f"   Metadata: {fetched.metadata}")

        # 5. Update order status
        print("\n5. Updating order status...")
        updated = await manager.update_order_status(
            order1.id,
            OrderStatus.OPEN
        )
        print(f"   Status updated to: {updated.status.value}")

        # 6. Partial fill
        print("\n6. Partially filling order...")
        partial = await manager.update_order_status(
            order1.id,
            OrderStatus.PARTIALLY_FILLED,
            filled_size=40.0
        )
        print(f"   Filled size: {partial.filled_size}")
        print(f"   Remaining: {partial.remaining_size}")

        # 7. Complete fill
        print("\n7. Completing order fill...")
        filled = await manager.update_order_status(
            order1.id,
            OrderStatus.FILLED,
            filled_size=100.0
        )
        print(f"   Final status: {filled.status.value}")
        print(f"   Filled at: {filled.filled_at}")

        # 8. Cancel remaining order
        print("\n8. Cancelling remaining order...")
        cancelled = await order_manager.cancel_order(order2.id)
        print(f"   Cancelled order: {cancelled.id}")
        print(f"   Cancelled at: {cancelled.cancelled_at}")

        manager.close()
        print("\n✓ Basic usage example completed successfully!")

    finally:
        Path(db_path).unlink(missing_ok=True)


async def example_status_callbacks():
    """Example: Status change callbacks."""
    print("\n" + "=" * 60)
    print("Example: Status Change Callbacks")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = OrderManager(db_path=db_path)

        # Track status changes
        status_changes = []

        def on_status_change(order, new_status):
            change = {
                "order_id": order.id,
                "new_status": new_status.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            status_changes.append(change)
            print(f"   📊 Status change: {order.id[:20]}... -> {new_status.value}")

        # Register callback
        manager.add_status_callback(on_status_change)
        print("✓ Status callback registered")

        # Create order
        print("\n1. Creating order...")
        order = await manager.create_order(
            market_id="market-123",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
            order_type=OrderType.LIMIT
        )
        print(f"   Created: {order.id}")

        # Update status multiple times
        print("\n2. Transitioning through statuses...")
        await manager.update_order_status(order.id, OrderStatus.OPEN)
        await manager.update_order_status(order.id, OrderStatus.PARTIALLY_FILLED, filled_size=30.0)
        await manager.update_order_status(order.id, OrderStatus.FILLED, filled_size=100.0)

        print(f"\n3. Total status changes tracked: {len(status_changes)}")
        for change in status_changes:
            print(f"   - {change['order_id'][:20]}... -> {change['new_status']}")

        # Remove callback
        manager.remove_status_callback(on_status_change)
        print("\n✓ Status callback removed")

        manager.close()
        print("\n✓ Status callbacks example completed successfully!")

    finally:
        Path(db_path).unlink(missing_ok=True)


async def example_statistics():
    """Example: Order statistics."""
    print("\n" + "=" * 60)
    print("Example: Order Statistics")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = OrderManager(db_path=db_path)

        # Create various orders
        print("\n1. Creating diverse set of orders...")

        # Filled orders
        for i in range(3):
            order = await manager.create_order(
                market_id="market-A",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                size=100.0 + i * 10,
                price=0.5 + i * 0.01,
                order_type=OrderType.LIMIT
            )
            await manager.update_order_status(order.id, OrderStatus.FILLED, filled_size=order.size)
            print(f"   Created filled order: {order.id[:20]}... ({order.side.value} {order.size})")

        # Cancelled orders
        for i in range(2):
            order = await manager.create_order(
                market_id="market-B",
                side=OrderSide.SELL,
                size=50.0 + i * 5,
                price=0.6,
                order_type=OrderType.LIMIT
            )
            await manager.cancel_order(order.id)
            print(f"   Created cancelled order: {order.id[:20]}...")

        # Pending orders
        for i in range(2):
            order = await manager.create_order(
                market_id="market-C",
                side=OrderSide.BUY,
                size=200.0,
                price=0.45,
                order_type=OrderType.LIMIT
            )
            print(f"   Created pending order: {order.id[:20]}...")

        # Get statistics
        print("\n2. Getting order statistics...")
        stats = await manager.get_order_stats()

        print(f"\n   📊 Overall Statistics:")
        print(f"      Total Orders: {stats['total_orders']}")
        print(f"      Active Orders: {stats['active_orders']}")

        print(f"\n   📈 Status Breakdown:")
        for status, count in stats['status_breakdown'].items():
            print(f"      {status}: {count}")

        print(f"\n   💰 Filled Statistics:")
        filled = stats['filled_statistics']
        print(f"      Total Filled Size: {filled['total_filled_size']:.2f}")
        print(f"      Total Filled Value: ${filled['total_filled_value']:.2f}")
        print(f"      Filled Order Count: {filled['filled_count']}")

        # Get market-specific stats
        print("\n3. Getting market-specific statistics...")
        market_stats = await manager.get_order_stats(market_id="market-A")
        print(f"   Market A - Total Orders: {market_stats['total_orders']}")
        print(f"   Market A - Filled: {market_stats['status_breakdown'].get('filled', 0)}")

        manager.close()
        print("\n✓ Statistics example completed successfully!")

    finally:
        Path(db_path).unlink(missing_ok=True)


async def example_market_scenario():
    """Example: Realistic market trading scenario."""
    print("\n" + "=" * 60)
    print("Example: Realistic Market Trading Scenario")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = OrderManager(db_path=db_path)

        # Set up status tracking
        def on_status_change(order, new_status):
            emoji = {
                OrderStatus.PENDING: "⏳",
                OrderStatus.OPEN: "📤",
                OrderStatus.PARTIALLY_FILLED: "🔄",
                OrderStatus.FILLED: "✅",
                OrderStatus.CANCELLED: "❌",
                OrderStatus.REJECTED: "🚫"
            }.get(new_status, "❓")

            print(f"   {emoji} Order {order.id[:20]}... status: {new_status.value}")

        manager.add_status_callback(on_status_change)

        print("\n📊 Scenario: Trading Session")
        print("-" * 40)

        # Market parameters
        market_id = "0x1234567890abcdef1234567890abcdef"

        # Step 1: Place initial buy orders
        print("\n1️⃣ Placing initial buy orders...")
        buy_orders = []
        for i in range(3):
            order = await manager.create_order(
                market_id=market_id,
                side=OrderSide.BUY,
                size=100.0 + i * 50,
                price=0.45 + i * 0.01,
                order_type=OrderType.LIMIT,
                metadata={"batch": "initial", "index": i}
            )
            buy_orders.append(order)
            print(f"   📈 Created BUY order: {order.size} @ {order.price}")

        # Step 2: Update orders to open (simulating exchange acceptance)
        print("\n2️⃣ Orders accepted by exchange...")
        for order in buy_orders:
            await manager.update_order_status(order.id, OrderStatus.OPEN)

        # Step 3: Place a sell order
        print("\n3️⃣ Placing sell order...")
        sell_order = await manager.create_order(
            market_id=market_id,
            side=OrderSide.SELL,
            size=75.0,
            price=0.55,
            order_type=OrderType.LIMIT,
            metadata={"strategy": "profit_taking"}
        )
        print(f"   📉 Created SELL order: {sell_order.size} @ {sell_order.price}")
        await manager.update_order_status(sell_order.id, OrderStatus.OPEN)

        # Step 4: Partial fill on first buy order
        print("\n4️⃣ First buy order partially filled...")
        await manager.update_order_status(
            buy_orders[0].id,
            OrderStatus.PARTIALLY_FILLED,
            filled_size=60.0
        )
        print(f"   🔄 Filled 60 / {buy_orders[0].size}")

        # Step 5: Complete fill on first buy order
        print("\n5️⃣ First buy order completely filled...")
        await manager.update_order_status(
            buy_orders[0].id,
            OrderStatus.FILLED,
            filled_size=100.0
        )
        print(f"   ✅ Total filled: 100 / 100")

        # Step 6: Cancel one of the remaining buy orders
        print("\n6️⃣ Cancelling second buy order...")
        await manager.cancel_order(buy_orders[1].id)
        print(f"   ❌ Order cancelled")

        # Step 7: Get current positions
        print("\n7️⃣ Current order status summary:")
        print("-" * 40)

        stats = await manager.get_order_stats(market_id=market_id)
        print(f"   Total Orders: {stats['total_orders']}")
        print(f"   Active Orders: {stats['active_orders']}")

        for status, count in stats['status_breakdown'].items():
            emoji = {
                'pending': '⏳',
                'open': '📤',
                'partially_filled': '🔄',
                'filled': '✅',
                'cancelled': '❌',
                'rejected': '🚫'
            }.get(status, '❓')
            print(f"   {emoji} {status}: {count}")

        # Step 8: Get filled order details
        print("\n8️⃣ Filled order details:")
        filled_orders = await manager.list_orders(status=OrderStatus.FILLED)
        for order in filled_orders:
            print(f"   ✅ {order.id[:25]}...")
            print(f"      Side: {order.side.value.upper()}")
            print(f"      Size: {order.size} @ {order.price}")
            print(f"      Filled at: {order.filled_at}")

        # Step 9: Get active orders
        print("\n9️⃣ Active orders (should be tracked in cache):")
        active = await manager.get_active_orders_from_cache()
        print(f"   Active orders in cache: {len(active)}")
        for order in active:
            print(f"   📌 {order.id[:25]}... - {order.status.value}")

        # Step 10: Cancel all remaining orders
        print("\n🔟 Cancelling all remaining orders...")
        cancelled = await manager.cancel_all_orders()
        print(f"   Cancelled {len(cancelled)} orders")

        print("\n✅ Trading session completed!")
        print("=" * 60)

        manager.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


async def example_singleton_pattern():
    """Example: Using the singleton pattern."""
    print("\n" + "=" * 60)
    print("Example: Singleton Pattern")
    print("=" * 60)

    # Reset any existing singleton
    reset_order_manager()

    # Get the singleton instance
    print("\n1. Getting singleton instance...")
    manager1 = get_order_manager()
    print(f"   Manager 1 ID: {id(manager1)}")

    # Get it again - should be the same instance
    manager2 = get_order_manager()
    print(f"   Manager 2 ID: {id(manager2)}")
    print(f"   Same instance: {manager1 is manager2}")

    # Create an order through the singleton
    print("\n2. Creating order through singleton...")
    order = await manager1.create_order(
        market_id="singleton-test",
        side=OrderSide.BUY,
        size=100.0,
        price=0.5,
        order_type=OrderType.LIMIT
    )
    print(f"   Created order: {order.id[:25]}...")

    # Access it from the other reference
    fetched = await manager2.get_order(order.id)
    print(f"   Retrieved via manager2: {fetched.id[:25]}...")

    # Reset singleton
    print("\n3. Resetting singleton...")
    reset_order_manager()
    manager3 = get_order_manager()
    print(f"   Manager 3 ID: {id(manager3)}")
    print(f"   Different from manager1: {manager1 is not manager3}")

    manager3.close()
    print("\n✅ Singleton pattern example completed!")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Polymarket Order Manager - Examples")
    print("=" * 60)

    # Run examples
    await example_basic_usage()
    await example_singleton_pattern()

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())