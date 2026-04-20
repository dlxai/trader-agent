"""
Polymarket integration package.

This package provides tools for interacting with the Polymarket
prediction market platform, including:

- Client: Direct API interaction
- OrderManager: Order lifecycle management
- MarketData: Market data retrieval
"""

from polymarket.client import (
    PolymarketClient,
    Market,
    OrderBook,
    Balance,
    Position,
    PolymarketAPIError,
    PolymarketAuthError,
    PolymarketRateLimitError,
    PolymarketTimeoutError,
    PolymarketValidationError,
    retry_with_exponential_backoff,
    create_client,
    get_client_from_env,
)
from polymarket.order_manager import (
    OrderManager,
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
    get_order_manager,
    reset_order_manager,
)
from polymarket.market_data import MarketDataManager

__all__ = [
    # Client
    "PolymarketClient",
    # Data Classes
    "Market",
    "OrderBook",
    "Balance",
    "Position",
    # Exceptions
    "PolymarketAPIError",
    "PolymarketAuthError",
    "PolymarketRateLimitError",
    "PolymarketTimeoutError",
    "PolymarketValidationError",
    # Decorators and Utilities
    "retry_with_exponential_backoff",
    "create_client",
    "get_client_from_env",
    # Order Manager
    "OrderManager",
    "Order",
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "get_order_manager",
    "reset_order_manager",
    # Market Data
    "MarketDataManager",
]

__version__ = "0.1.0"