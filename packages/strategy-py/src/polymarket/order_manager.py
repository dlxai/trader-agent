"""
Polymarket Order Manager

Manages order lifecycle, tracks order status, and provides SQLite persistence.
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Union
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration."""
    LIMIT = "limit"
    MARKET = "market"
    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate or Cancel


@dataclass
class Order:
    """Represents a single order."""
    id: str
    market_id: str
    side: OrderSide
    size: float
    price: float
    order_type: OrderType
    status: OrderStatus = field(default=OrderStatus.PENDING)
    filled_size: float = field(default=0.0)
    remaining_size: float = field(default=0.0)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    cancelled_at: Optional[datetime] = field(default=None)
    filled_at: Optional[datetime] = field(default=None)
    reject_reason: Optional[str] = field(default=None)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize remaining size if not set."""
        if self.remaining_size == 0.0 and self.filled_size == 0.0:
            self.remaining_size = self.size

    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "side": self.side.value,
            "size": self.size,
            "price": self.price,
            "order_type": self.order_type.value,
            "status": self.status.value,
            "filled_size": self.filled_size,
            "remaining_size": self.remaining_size,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "reject_reason": self.reject_reason,
            "metadata": json.dumps(self.metadata)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        """Create order from dictionary."""
        return cls(
            id=data["id"],
            market_id=data["market_id"],
            side=OrderSide(data["side"]),
            size=float(data["size"]),
            price=float(data["price"]),
            order_type=OrderType(data["order_type"]),
            status=OrderStatus(data["status"]),
            filled_size=float(data.get("filled_size", 0)),
            remaining_size=float(data.get("remaining_size", 0)),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            cancelled_at=datetime.fromisoformat(data["cancelled_at"]) if data.get("cancelled_at") else None,
            filled_at=datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None,
            reject_reason=data.get("reject_reason"),
            metadata=json.loads(data.get("metadata", "{}"))
        )


# Type alias for status change callbacks
StatusChangeCallback = Callable[[Order, OrderStatus], None]


class OrderManager:
    """
    Manages order lifecycle, tracks order status, and provides SQLite persistence.

    Features:
    - Order CRUD operations
    - Status tracking and transitions
    - SQLite persistence
    - Status change callbacks
    - Active and historical order tracking
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize OrderManager.

        Args:
            db_path: Path to SQLite database. If None, uses in-memory database.
            max_retries: Maximum number of retries for failed operations.
            retry_delay: Delay between retries in seconds.
        """
        self.db_path = db_path or ":memory:"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # In-memory caches
        self._active_orders: Dict[str, Order] = {}
        self._status_callbacks: List[StatusChangeCallback] = []
        self._lock = asyncio.Lock()

        # Initialize database
        self._init_db()
        logger.info(f"OrderManager initialized with database: {self.db_path}")

    def _init_db(self) -> None:
        """Initialize SQLite database with required tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    price REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    filled_size REAL DEFAULT 0,
                    remaining_size REAL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    filled_at TEXT,
                    reject_reason TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Create index on status for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)
            """)

            # Create index on market_id for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_market ON orders(market_id)
            """)

            conn.commit()
            logger.debug("Database initialized successfully")

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def add_status_callback(self, callback: StatusChangeCallback) -> None:
        """
        Add a callback for order status changes.

        Args:
            callback: Function to call when order status changes.
                     Signature: callback(order, new_status)
        """
        self._status_callbacks.append(callback)
        logger.debug(f"Status callback added. Total callbacks: {len(self._status_callbacks)}")

    def remove_status_callback(self, callback: StatusChangeCallback) -> None:
        """
        Remove a status change callback.

        Args:
            callback: Callback function to remove.
        """
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
            logger.debug(f"Status callback removed. Total callbacks: {len(self._status_callbacks)}")

    def _notify_status_change(self, order: Order, old_status: OrderStatus) -> None:
        """Notify all callbacks of status change."""
        if old_status != order.status:
            logger.info(f"Order {order.id} status changed: {old_status.value} -> {order.status.value}")
            for callback in self._status_callbacks:
                try:
                    callback(order, order.status)
                except Exception as e:
                    logger.error(f"Error in status callback: {e}")

    async def create_order(
        self,
        market_id: str,
        side: Union[OrderSide, str],
        size: float,
        price: float,
        order_type: Union[OrderType, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Order:
        """
        Create a new order.

        Args:
            market_id: Market identifier
            side: Order side (BUY or SELL)
            size: Order size
            price: Order price
            order_type: Type of order (LIMIT, MARKET, etc.)
            metadata: Optional additional metadata

        Returns:
            Created Order object

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order creation fails after retries
        """
        # Validate and convert enums
        if isinstance(side, str):
            side = OrderSide(side.lower())
        if isinstance(order_type, str):
            order_type = OrderType(order_type.lower())

        # Validate parameters
        if size <= 0:
            raise ValueError(f"Order size must be positive, got {size}")
        if price <= 0:
            raise ValueError(f"Order price must be positive, got {price}")
        if not market_id:
            raise ValueError("Market ID cannot be empty")

        # Generate unique order ID
        order_id = f"ord_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{market_id[:8]}"

        # Create order object
        order = Order(
            id=order_id,
            market_id=market_id,
            side=side,
            size=size,
            price=price,
            order_type=order_type,
            status=OrderStatus.PENDING,
            filled_size=0.0,
            remaining_size=size,
            metadata=metadata or {}
        )

        # Save to database with retry logic
        for attempt in range(self.max_retries):
            try:
                await self._save_order(order)
                break
            except Exception as e:
                logger.warning(f"Failed to save order (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise RuntimeError(f"Failed to create order after {self.max_retries} attempts: {e}")

        # Add to active orders cache
        async with self._lock:
            self._active_orders[order_id] = order

        logger.info(f"Order created: {order_id} for market {market_id}")
        return order

    async def _save_order(self, order: Order) -> None:
        """Save order to database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            order_dict = order.to_dict()

            columns = ", ".join(order_dict.keys())
            placeholders = ", ".join(["?"] * len(order_dict))

            query = f"""
                INSERT OR REPLACE INTO orders ({columns})
                VALUES ({placeholders})
            """

            cursor.execute(query, list(order_dict.values()))
            conn.commit()

    async def cancel_order(self, order_id: str) -> Order:
        """
        Cancel an existing order.

        Args:
            order_id: ID of order to cancel

        Returns:
            Updated Order object

        Raises:
            ValueError: If order not found
            RuntimeError: If cancellation fails after retries
        """
        # Get current order
        order = await self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        # Check if order can be cancelled
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            logger.warning(f"Cannot cancel order {order_id} with status {order.status.value}")
            return order

        old_status = order.status

        # Update order status
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()

        # Save with retry logic
        for attempt in range(self.max_retries):
            try:
                await self._save_order(order)
                break
            except Exception as e:
                logger.warning(f"Failed to cancel order (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    # Revert status on failure
                    order.status = old_status
                    order.cancelled_at = None
                    raise RuntimeError(f"Failed to cancel order after {self.max_retries} attempts: {e}")

        # Update cache
        async with self._lock:
            if order_id in self._active_orders:
                del self._active_orders[order_id]

        # Notify callbacks
        self._notify_status_change(order, old_status)

        logger.info(f"Order cancelled: {order_id}")
        return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order by ID.

        Args:
            order_id: Order ID to look up

        Returns:
            Order object if found, None otherwise
        """
        # Check cache first
        async with self._lock:
            if order_id in self._active_orders:
                return self._active_orders[order_id]

        # Query database
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = cursor.fetchone()

                if row:
                    order_dict = dict(row)
                    order = Order.from_dict(order_dict)

                    # Add to cache if active
                    if order.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                        async with self._lock:
                            self._active_orders[order_id] = order

                    return order
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")

        return None

    async def list_orders(
        self,
        status: Optional[Union[OrderStatus, str]] = None,
        market_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Order]:
        """
        List orders with optional filtering.

        Args:
            status: Filter by order status
            market_id: Filter by market ID
            limit: Maximum number of orders to return
            offset: Number of orders to skip

        Returns:
            List of Order objects
        """
        # Convert string status to enum if needed
        if isinstance(status, str):
            status = OrderStatus(status.lower())

        # Build query
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status.value)

        if market_id:
            conditions.append("market_id = ?")
            params.append(market_id)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        orders = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    order_dict = dict(row)
                    orders.append(Order.from_dict(order_dict))
        except Exception as e:
            logger.error(f"Error listing orders: {e}")
            raise

        return orders

    async def update_order_status(
        self,
        order_id: str,
        new_status: Union[OrderStatus, str],
        filled_size: Optional[float] = None,
        reject_reason: Optional[str] = None
    ) -> Order:
        """
        Update order status and related fields.

        Args:
            order_id: Order ID to update
            new_status: New order status
            filled_size: New filled size (if applicable)
            reject_reason: Reason for rejection (if applicable)

        Returns:
            Updated Order object

        Raises:
            ValueError: If order not found
        """
        # Convert string status to enum if needed
        if isinstance(new_status, str):
            new_status = OrderStatus(new_status.lower())

        # Get current order
        order = await self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        old_status = order.status

        # Update status
        order.status = new_status
        order.updated_at = datetime.utcnow()

        # Update filled size if provided
        if filled_size is not None:
            order.filled_size = filled_size
            order.remaining_size = order.size - filled_size

        # Update reject reason if provided
        if reject_reason:
            order.reject_reason = reject_reason

        # Update timestamps based on status
        if new_status == OrderStatus.FILLED:
            order.filled_at = datetime.utcnow()
            order.remaining_size = 0
            order.filled_size = order.size
        elif new_status == OrderStatus.CANCELLED:
            order.cancelled_at = datetime.utcnow()
        elif new_status == OrderStatus.PARTIALLY_FILLED and filled_size:
            if order.filled_size + filled_size >= order.size:
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.utcnow()

        # Save to database
        await self._save_order(order)

        # Update cache
        async with self._lock:
            if new_status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
                if order_id in self._active_orders:
                    del self._active_orders[order_id]
            else:
                self._active_orders[order_id] = order

        # Notify callbacks
        self._notify_status_change(order, old_status)

        logger.info(f"Order {order_id} status updated: {old_status.value} -> {new_status.value}")
        return order

    async def get_active_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """
        Get all active orders (PENDING, OPEN, PARTIALLY_FILLED).

        Args:
            market_id: Optional market ID filter

        Returns:
            List of active Order objects
        """
        return await self.list_orders(
            status=None,  # We'll filter in the query
            market_id=market_id
        )

    async def get_active_orders_from_cache(self, market_id: Optional[str] = None) -> List[Order]:
        """
        Get active orders from cache for faster access.

        Args:
            market_id: Optional market ID filter

        Returns:
            List of active Order objects
        """
        async with self._lock:
            orders = list(self._active_orders.values())

        if market_id:
            orders = [o for o in orders if o.market_id == market_id]

        return orders

    async def get_order_history(
        self,
        market_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get historical orders with filtering.

        Args:
            market_id: Filter by market ID
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of orders

        Returns:
            List of historical Order objects
        """
        # Build query
        conditions = ["status IN (?, ?, ?)"]
        params = [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value]

        if market_id:
            conditions.append("market_id = ?")
            params.append(market_id)

        if start_time:
            conditions.append("created_at >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("created_at <= ?")
            params.append(end_time.isoformat())

        where_clause = " WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT * FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        orders = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    order_dict = dict(row)
                    orders.append(Order.from_dict(order_dict))
        except Exception as e:
            logger.error(f"Error getting order history: {e}")
            raise

        return orders

    async def cancel_all_orders(
        self,
        market_id: Optional[str] = None,
        status_filter: Optional[List[OrderStatus]] = None
    ) -> List[Order]:
        """
        Cancel all orders matching criteria.

        Args:
            market_id: Filter by market ID
            status_filter: List of statuses to cancel (default: cancellable statuses)

        Returns:
            List of cancelled Order objects
        """
        if status_filter is None:
            status_filter = [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]

        # Get orders to cancel
        orders = await self.list_orders(status=None, market_id=market_id)
        orders_to_cancel = [o for o in orders if o.status in status_filter]

        cancelled_orders = []
        for order in orders_to_cancel:
            try:
                cancelled = await self.cancel_order(order.id)
                cancelled_orders.append(cancelled)
            except Exception as e:
                logger.error(f"Failed to cancel order {order.id}: {e}")

        logger.info(f"Cancelled {len(cancelled_orders)} orders")
        return cancelled_orders

    async def get_order_stats(self, market_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get order statistics.

        Args:
            market_id: Optional market ID filter

        Returns:
            Dictionary with order statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build base query
            base_query = "FROM orders"
            params = []

            if market_id:
                base_query += " WHERE market_id = ?"
                params.append(market_id)

            # Get total count
            cursor.execute(f"SELECT COUNT(*) {base_query}", params)
            total_count = cursor.fetchone()[0]

            # Get counts by status
            cursor.execute(f"""
                SELECT status, COUNT(*) as count
                {base_query}
                GROUP BY status
            """, params)

            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

            # Get filled volume stats
            cursor.execute(f"""
                SELECT
                    SUM(filled_size * price) as total_filled_value,
                    SUM(filled_size) as total_filled_size,
                    COUNT(*) as filled_count
                {base_query}
                WHERE status = 'filled'
            """, params)

            row = cursor.fetchone()
            filled_stats = {
                "total_filled_value": row["total_filled_value"] or 0,
                "total_filled_size": row["total_filled_size"] or 0,
                "filled_count": row["filled_count"] or 0
            }

        return {
            "total_orders": total_count,
            "status_breakdown": status_counts,
            "filled_statistics": filled_stats,
            "active_orders": status_counts.get("pending", 0) +
                           status_counts.get("open", 0) +
                           status_counts.get("partially_filled", 0)
        }

    def close(self) -> None:
        """Close the order manager and cleanup resources."""
        self._active_orders.clear()
        self._status_callbacks.clear()
        logger.info("OrderManager closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()
        return False


# Singleton instance for shared access
_order_manager_instance: Optional[OrderManager] = None


def get_order_manager(
    db_path: Optional[Union[str, Path]] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> OrderManager:
    """
    Get or create the singleton OrderManager instance.

    Args:
        db_path: Path to SQLite database
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries

    Returns:
        OrderManager instance
    """
    global _order_manager_instance

    if _order_manager_instance is None:
        _order_manager_instance = OrderManager(
            db_path=db_path,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

    return _order_manager_instance


def reset_order_manager() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _order_manager_instance
    if _order_manager_instance:
        _order_manager_instance.close()
    _order_manager_instance = None