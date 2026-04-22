"""Polymarket client wrapper for backend."""

import sys
from pathlib import Path
from typing import Optional

# Add strategy-py source to path
# packages/backend-py/src/polymarket.py -> packages/strategy-py/src
_STRATEGY_PY_SRC = Path(__file__).resolve().parent.parent.parent / "strategy-py" / "src"
if str(_STRATEGY_PY_SRC) not in sys.path:
    sys.path.insert(0, str(_STRATEGY_PY_SRC))

# Import from strategy-py package if available
try:
    from polymarket.client import PolymarketClient, create_client
    POLYMARKET_CLIENT_AVAILABLE = True
except ImportError:
    POLYMARKET_CLIENT_AVAILABLE = False
    PolymarketClient = None
    create_client = None


def get_client(
    private_key: Optional[str] = None,
    proxy: Optional[str] = None,
    api_url: Optional[str] = None,
) -> Optional[PolymarketClient]:
    """Get a Polymarket client instance.

    Args:
        private_key: Ethereum private key (0x...)
        proxy: Proxy URL (e.g., http://127.0.0.1:7890)
        api_url: Custom API URL

    Returns:
        PolymarketClient instance or None if not available
    """
    if not POLYMARKET_CLIENT_AVAILABLE:
        return None

    return create_client(
        private_key=private_key,
        proxy=proxy or "http://127.0.0.1:7890",  # Default proxy
        api_url=api_url,
    )


def is_available() -> bool:
    """Check if Polymarket client is available."""
    return POLYMARKET_CLIENT_AVAILABLE
