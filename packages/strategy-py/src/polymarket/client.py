"""
Polymarket API Client

A comprehensive client for interacting with the Polymarket CLOB API.
Provides market data access, account management, and trading functionality.

Dependencies:
    - py-clob-client>=0.2.0
    - requests>=2.28.0

Example:
    >>> client = PolymarketClient(
    ...     private_key="0x...",
    ...     api_url="https://clob.polymarket.com"
    ... )
    >>> markets = client.get_markets(limit=10)
    >>> print(f"Found {len(markets)} markets")
"""

import logging
import time
import os
from typing import Any, Optional, Dict, List, Union, Callable
from dataclasses import dataclass, field
from functools import wraps
from datetime import datetime
import json

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Custom Exceptions ====================

class PolymarketAPIError(Exception):
    """Base exception for Polymarket API errors.

    Attributes:
        message: Error message
        status_code: HTTP status code if applicable
        response_data: Raw response data from API
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class PolymarketAuthError(PolymarketAPIError):
    """Authentication error - invalid or missing credentials."""
    pass


class PolymarketRateLimitError(PolymarketAPIError):
    """Rate limit exceeded - too many requests."""
    pass


class PolymarketTimeoutError(PolymarketAPIError):
    """Request timeout - server did not respond in time."""
    pass


class PolymarketValidationError(PolymarketAPIError):
    """Validation error - invalid parameters."""
    pass


# ==================== Data Classes ====================

@dataclass
class Market:
    """Market data structure representing a Polymarket prediction market.

    Attributes:
        id: Unique market identifier
        question: Market question text
        description: Detailed market description
        category: Market category
        end_date: Market resolution date
        status: Market status (active, resolved, etc.)
        volume: Total trading volume in USDC
        liquidity: Available liquidity
        outcomes: List of possible outcomes
        outcome_prices: Current prices for each outcome
    """
    id: str
    question: str
    description: str = ""
    category: str = ""
    end_date: Optional[str] = None
    status: str = "active"
    volume: float = 0.0
    liquidity: float = 0.0
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    outcome_prices: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Market":
        """Create Market from API response.

        Args:
            data: Raw API response data

        Returns:
            Market instance
        """
        # Parse volume - handle various formats
        volume = data.get("volume", 0)
        if isinstance(volume, str):
            try:
                volume = float(volume.replace(",", ""))
            except ValueError:
                volume = 0

        # Parse liquidity
        liquidity = data.get("liquidity", 0)
        if isinstance(liquidity, str):
            try:
                liquidity = float(liquidity.replace(",", ""))
            except ValueError:
                liquidity = 0

        # Parse outcomes
        outcomes = data.get("outcomes", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []

        # Parse outcome prices
        outcome_prices = data.get("outcomePrices", {})
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except json.JSONDecodeError:
                outcome_prices = {}

        # Convert price strings to floats
        parsed_prices = {}
        for key, value in outcome_prices.items():
            if isinstance(value, str):
                try:
                    parsed_prices[key] = float(value)
                except ValueError:
                    parsed_prices[key] = 0.0
            elif isinstance(value, (int, float)):
                parsed_prices[key] = float(value)

        return cls(
            id=data.get("id") or data.get("market_slug") or data.get("conditionId", ""),
            question=data.get("question", data.get("title", "")),
            description=data.get("description", ""),
            category=data.get("category", ""),
            end_date=data.get("endDate") or data.get("resolutionTime") or data.get("end_date"),
            status=data.get("status", data.get("active", True)),
            volume=float(volume) if volume else 0.0,
            liquidity=float(liquidity) if liquidity else 0.0,
            outcomes=outcomes if isinstance(outcomes, list) else [],
            outcome_prices=parsed_prices,
        )


@dataclass
class OrderBook:
    """Order book data structure representing bids and asks.

    Attributes:
        token_id: Token identifier for the outcome
        bids: List of bid orders (price descending)
        asks: List of ask orders (price ascending)
        timestamp: Order book snapshot time
        market_slug: Optional market identifier
    """
    token_id: str
    bids: List[Dict[str, Any]] = field(default_factory=list)
    asks: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: Optional[int] = None
    market_slug: Optional[str] = None

    @classmethod
    def from_api_response(cls, token_id: str, data: Dict[str, Any]) -> "OrderBook":
        """Create OrderBook from API response.

        Args:
            token_id: Token identifier
            data: Raw API response data

        Returns:
            OrderBook instance
        """
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        # Ensure bids are sorted by price descending (best bid first)
        if bids:
            bids = sorted(bids, key=lambda x: float(x.get("price", 0)), reverse=True)

        # Ensure asks are sorted by price ascending (best ask first)
        if asks:
            asks = sorted(asks, key=lambda x: float(x.get("price", 0)))

        return cls(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=data.get("timestamp"),
            market_slug=data.get("market_slug"),
        )

    @property
    def best_bid(self) -> Optional[float]:
        """Get best bid price."""
        if self.bids:
            return float(self.bids[0].get("price", 0))
        return None

    @property
    def best_ask(self) -> Optional[float]:
        """Get best ask price."""
        if self.asks:
            return float(self.asks[0].get("price", 0))
        return None

    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price."""
        bid = self.best_bid
        ask = self.best_ask
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return bid or ask


@dataclass
class Balance:
    """Account balance data structure.

    Attributes:
        usdc_balance: Available USDC balance
        usdc_allowance: Approved USDC amount for trading
        weth_balance: Optional WETH balance
        last_updated: Timestamp of last update
    """
    usdc_balance: float = 0.0
    usdc_allowance: float = 0.0
    weth_balance: Optional[float] = None
    last_updated: Optional[datetime] = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Balance":
        """Create Balance from API response.

        Args:
            data: Raw API response data

        Returns:
            Balance instance
        """
        def parse_value(value: Any) -> float:
            """Parse numeric value from various formats."""
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.replace(",", ""))
                except ValueError:
                    return 0.0
            return 0.0

        weth = data.get("weth_balance")

        return cls(
            usdc_balance=parse_value(data.get("usdc_balance") or data.get("cash") or data.get("balance", 0)),
            usdc_allowance=parse_value(data.get("usdc_allowance") or data.get("allowance", 0)),
            weth_balance=parse_value(weth) if weth is not None else None,
            last_updated=datetime.now(),
        )

    @property
    def effective_balance(self) -> float:
        """Get effective balance considering allowance."""
        return min(self.usdc_balance, self.usdc_allowance) if self.usdc_allowance > 0 else self.usdc_balance

    def __str__(self) -> str:
        """String representation of balance."""
        parts = [f"USDC: {self.usdc_balance:.2f}"]
        if self.usdc_allowance > 0:
            parts.append(f"Allowance: {self.usdc_allowance:.2f}")
        if self.weth_balance is not None:
            parts.append(f"WETH: {self.weth_balance:.4f}")
        return " | ".join(parts)


@dataclass
class Position:
    """Position data structure representing a trading position.

    Attributes:
        market_id: Market identifier
        token_id: Token identifier for the outcome
        outcome: Outcome name
        quantity: Position size
        avg_buy_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        last_updated: Position update timestamp
    """
    market_id: str
    token_id: str
    outcome: str
    quantity: float = 0.0
    avg_buy_price: float = 0.0
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    last_updated: Optional[datetime] = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Position":
        """Create Position from API response.

        Args:
            data: Raw API response data

        Returns:
            Position instance
        """
        def parse_float(value: Any, default: float = 0.0) -> float:
            """Parse float value safely."""
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.replace(",", ""))
                except ValueError:
                    return default
            return default

        # Parse current price
        current_price = data.get("current_price")
        if current_price is not None:
            current_price = parse_float(current_price)

        # Parse unrealized PnL
        unrealized_pnl = data.get("unrealized_pnl")
        if unrealized_pnl is not None:
            unrealized_pnl = parse_float(unrealized_pnl)

        # Parse last updated
        last_updated = None
        ts = data.get("last_updated") or data.get("updated_at") or data.get("timestamp")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    last_updated = datetime.fromtimestamp(ts)
                elif isinstance(ts, str):
                    last_updated = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            market_id=data.get("market_id") or data.get("condition_id") or data.get("market_slug", ""),
            token_id=data.get("token_id") or data.get("asset_id", ""),
            outcome=data.get("outcome") or data.get("position") or "",
            quantity=parse_float(data.get("quantity") or data.get("size") or data.get("amount")),
            avg_buy_price=parse_float(data.get("avg_buy_price") or data.get("avg_price") or data.get("entry_price")),
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            last_updated=last_updated if last_updated else datetime.now(),
        )

    @property
    def market_value(self) -> float:
        """Calculate current market value of position."""
        if self.current_price is not None:
            return self.quantity * self.current_price
        return self.quantity * self.avg_buy_price

    @property
    def cost_basis(self) -> float:
        """Calculate cost basis of position."""
        return self.quantity * self.avg_buy_price

    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL given current price."""
        return self.quantity * (current_price - self.avg_buy_price)


# ==================== Retry Decorator ====================

def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (requests.exceptions.RequestException,),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
):
    """Decorator for retrying with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Multiplier for delay after each retry
        retryable_exceptions: Tuple of exceptions that trigger a retry
        on_retry: Optional callback function called on each retry

    Example:
        @retry_with_exponential_backoff(max_retries=3)
        def fetch_data():
            return requests.get(url)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}"
                        )
                        raise PolymarketAPIError(f"Max retries exceeded: {str(e)}") from e

                    # Check for rate limiting
                    if hasattr(e, 'response') and e.response is not None:
                        if e.response.status_code == 429:
                            logger.warning(f"Rate limit hit for {func.__name__}, using longer delay")
                            delay = min(delay * 2, max_delay)
                        # Handle auth errors
                        elif e.response.status_code == 401:
                            raise PolymarketAuthError("Authentication failed") from e
                        elif e.response.status_code == 403:
                            raise PolymarketAuthError("Access forbidden") from e

                    # Check for timeout
                    if isinstance(e, requests.exceptions.Timeout):
                        raise PolymarketTimeoutError(f"Request timeout after initial attempt") from e

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: "
                        f"{e}. Retrying in {delay:.1f}s..."
                    )

                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1, delay)
                        except Exception as callback_error:
                            logger.warning(f"Retry callback failed: {callback_error}")

                    time.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)

            raise PolymarketAPIError(
                f"Unexpected error after {max_retries} retries: {str(last_exception)}"
            ) from last_exception

        return wrapper
    return decorator


# ==================== Main Client Class ====================

class PolymarketClient:
    """
    Polymarket API Client

    A comprehensive client for interacting with the Polymarket CLOB API.
    Supports market data access, account management, and trading operations.

    Features:
        - Automatic retry with exponential backoff
        - Proxy support (default: http://127.0.0.1:7890)
        - Comprehensive error handling
        - Type hints throughout
        - Context manager support

    Example:
        >>> client = PolymarketClient(
        ...     private_key="0x...",
        ...     api_url="https://clob.polymarket.com"
        ... )
        >>>
        >>> # Get markets
        >>> markets = client.get_markets(limit=10)
        >>>
        >>> # Get order book
        >>> orderbook = client.get_orderbook(token_id="...")
        >>>
        >>> # Clean up
        >>> client.close()

        Or use as context manager:
        >>> with PolymarketClient(private_key="0x...") as client:
        ...     markets = client.get_markets()
    """

    DEFAULT_API_URL = "https://clob.polymarket.com"
    DEFAULT_GAMMA_API_URL = "https://gamma-api.polymarket.com"
    DEFAULT_PROXY = "http://127.0.0.1:7890"
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        gamma_api_url: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        enable_retries: bool = True,
        max_retries: int = 3,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        passphrase: Optional[str] = None
    ):
        """
        Initialize the PolymarketClient.

        Args:
            private_key: Ethereum private key for signing transactions (0x...)
            api_url: CLOB API endpoint URL (default: https://clob.polymarket.com)
            gamma_api_url: Gamma API endpoint URL for market data
                          (default: https://gamma-api.polymarket.com)
            proxy: Proxy URL (default: http://127.0.0.1:7890)
            timeout: Request timeout in seconds (default: 30)
            enable_retries: Enable automatic retry with exponential backoff (default: True)
            max_retries: Maximum number of retry attempts (default: 3)
            api_key: Optional API key for authentication
            secret: Optional API secret
            passphrase: Optional API passphrase

        Raises:
            ValueError: If invalid parameters are provided
        """
        self.private_key = private_key
        self.api_url = (api_url or self.DEFAULT_API_URL).rstrip("/")
        self.gamma_api_url = (gamma_api_url or self.DEFAULT_GAMMA_API_URL).rstrip("/")
        self.proxy = proxy or self.DEFAULT_PROXY
        self.timeout = timeout
        self.enable_retries = enable_retries
        self.max_retries = max_retries
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase

        # Statistics tracking
        self._api_calls = 0
        self._errors = 0
        self._retries = 0

        # Initialize session with proxy and retry configuration
        self.session = self._create_session()

        # Initialize py-clob-client if available and private key is provided
        self.clob_client = None
        if private_key:
            self._init_clob_client()

        logger.info(
            f"PolymarketClient initialized (API: {self.api_url}, "
            f"proxy: {self.proxy}, retries: {enable_retries})"
        )

    def _create_session(self) -> requests.Session:
        """Create a requests session with proxy and retry configuration.

        Returns:
            Configured requests.Session instance
        """
        session = requests.Session()

        # Configure proxy
        if self.proxy:
            session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            logger.debug(f"Proxy configured: {self.proxy}")

        # Configure retry strategy
        if self.enable_retries:
            retry_strategy = Retry(
                total=self.max_retries,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"],
                raise_on_status=False
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

        # Set default headers
        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "PolymarketClient/1.0"
        })

        return session

    def _init_clob_client(self) -> None:
        """Initialize py-clob-client if available."""
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            api_creds = None
            if self.api_key and self.secret:
                api_creds = ApiCreds(
                    api_key=self.api_key,
                    api_secret=self.secret,
                    api_passphrase=self.passphrase or ""
                )

            self.clob_client = ClobClient(
                host=self.api_url,
                key=self.private_key,
                chain_id=137,  # Polygon mainnet
                creds=api_creds
            )
            logger.info("py-clob-client initialized successfully")

        except ImportError:
            logger.warning(
                "py-clob-client not installed. "
                "Trading features will be limited. "
                "Install with: pip install py-clob-client>=0.2.0"
            )
            self.clob_client = None
        except Exception as e:
            logger.error(f"Failed to initialize py-clob-client: {e}")
            self.clob_client = None

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response and errors.

        Args:
            response: requests.Response object

        Returns:
            Parsed JSON response data

        Raises:
            PolymarketAPIError: If response indicates an error
            PolymarketAuthError: If authentication fails
            PolymarketRateLimitError: If rate limited
            PolymarketTimeoutError: If request times out
        """
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = response.status_code
            error_data = {}

            try:
                error_data = response.json()
            except (json.JSONDecodeError, ValueError):
                error_data = {"error": response.text}

            # Handle specific error types
            if status_code == 401:
                raise PolymarketAuthError(
                    "Authentication failed - check your credentials",
                    status_code, error_data
                ) from e
            elif status_code == 403:
                raise PolymarketAuthError(
                    "Access forbidden - insufficient permissions",
                    status_code, error_data
                ) from e
            elif status_code == 429:
                raise PolymarketRateLimitError(
                    "Rate limit exceeded - please slow down",
                    status_code, error_data
                ) from e
            elif status_code == 400:
                raise PolymarketValidationError(
                    f"Validation error: {error_data.get('error', 'Unknown')}",
                    status_code, error_data
                ) from e
            elif status_code >= 500:
                raise PolymarketAPIError(
                    f"Server error ({status_code}): {error_data.get('error', 'Unknown')}",
                    status_code, error_data
                ) from e
            else:
                raise PolymarketAPIError(
                    f"HTTP {status_code}: {error_data.get('error', response.text)}",
                    status_code, error_data
                ) from e

        except requests.exceptions.Timeout as e:
            raise PolymarketTimeoutError(
                f"Request timeout after {self.timeout}s"
            ) from e
        except requests.exceptions.RequestException as e:
            raise PolymarketAPIError(f"Request failed: {str(e)}") from e
        except json.JSONDecodeError as e:
            raise PolymarketAPIError(
                f"Invalid JSON response: {str(e)}"
            ) from e

    def _make_request(
        self,
        method: str,
        endpoint: str,
        base_url: Optional[str] = None,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            base_url: Base URL (defaults to self.api_url)
            params: Query parameters
            data: Request body data
            headers: Additional headers

        Returns:
            Parsed JSON response

        Raises:
            PolymarketAPIError: If request fails
        """
        url = f"{base_url or self.api_url}{endpoint}"

        request_headers = dict(self.session.headers)
        if headers:
            request_headers.update(headers)

        try:
            logger.debug(f"Making {method} request to {url}")
            self._api_calls += 1

            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=request_headers,
                timeout=self.timeout
            )
            return self._handle_response(response)

        except (PolymarketRateLimitError, PolymarketTimeoutError):
            raise
        except PolymarketAPIError:
            self._errors += 1
            raise
        except Exception as e:
            self._errors += 1
            logger.error(f"Unexpected error in request: {e}")
            raise PolymarketAPIError(f"Unexpected error: {str(e)}") from e

    # ==================== Market Data Methods ====================

    def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = True,
        category: Optional[str] = None,
        sort_by: str = "volume",
        descending: bool = True
    ) -> List[Market]:
        """Get list of markets.

        Args:
            limit: Maximum number of markets to return (default: 100)
            offset: Pagination offset (default: 0)
            active_only: Only return active markets (default: True)
            category: Filter by category (optional)
            sort_by: Sort field - "volume", "liquidity", "created" (default: "volume")
            descending: Sort in descending order (default: True)

        Returns:
            List of Market objects

        Raises:
            PolymarketAPIError: If the API request fails
            PolymarketValidationError: If parameters are invalid

        Example:
            >>> markets = client.get_markets(limit=10, active_only=True)
            >>> for market in markets:
            ...     print(f"{market.question}: ${market.volume:,.0f}")
        """
        # Validate parameters
        if limit < 1 or limit > 1000:
            raise PolymarketValidationError("limit must be between 1 and 1000")
        if offset < 0:
            raise PolymarketValidationError("offset must be non-negative")

        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        # Add optional filters
        if active_only:
            params["active"] = "true"
        if category:
            params["category"] = category
        if sort_by in ["volume", "liquidity", "created", "end_date"]:
            params["sort"] = sort_by
            params["order"] = "desc" if descending else "asc"

        try:
            # Try Gamma API first for market data (more reliable)
            data = self._make_request(
                "GET",
                "/markets",
                base_url=self.gamma_api_url,
                params=params
            )

            markets = []

            # Handle different response formats
            if isinstance(data, dict):
                market_list = data.get("markets", data.get("data", []))
            elif isinstance(data, list):
                market_list = data
            else:
                market_list = []

            if not isinstance(market_list, list):
                logger.warning(f"Unexpected response format: {type(market_list)}")
                market_list = []

            for market_data in market_list:
                try:
                    if not isinstance(market_data, dict):
                        logger.warning(f"Skipping non-dict market data: {type(market_data)}")
                        continue
                    market = Market.from_api_response(market_data)
                    markets.append(market)
                except Exception as e:
                    logger.warning(f"Failed to parse market data: {e}")
                    continue

            logger.info(f"Retrieved {len(markets)} markets (requested {limit})")
            return markets

        except PolymarketAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            raise PolymarketAPIError(f"Failed to get markets: {str(e)}") from e

    def get_market_by_id(self, market_id: str) -> Market:
        """Get market details by ID.

        Args:
            market_id: Market ID or slug (e.g., "will-bitcoin-hit-100k")

        Returns:
            Market object with full details

        Raises:
            PolymarketAPIError: If the market is not found or request fails
            PolymarketValidationError: If market_id is invalid

        Example:
            >>> market = client.get_market_by_id("will-bitcoin-hit-100k")
            >>> print(f"{market.question}")
            >>> print(f"Volume: ${market.volume:,.0f}")
        """
        if not market_id or not isinstance(market_id, str):
            raise PolymarketValidationError("Market ID must be a non-empty string")

        market_id = market_id.strip()

        try:
            # Try Gamma API first for market data
            data = self._make_request(
                "GET",
                f"/markets/{market_id}",
                base_url=self.gamma_api_url
            )

            if not data or not isinstance(data, dict):
                raise PolymarketAPIError(f"Invalid response for market {market_id}")

            market = Market.from_api_response(data)
            logger.info(f"Retrieved market: {market.question[:50]}...")
            return market

        except PolymarketAPIError as e:
            if e.status_code == 404:
                raise PolymarketAPIError(
                    f"Market not found: {market_id}",
                    404
                ) from e
            raise
        except Exception as e:
            logger.error(f"Failed to get market {market_id}: {e}")
            raise PolymarketAPIError(f"Failed to get market: {str(e)}") from e

    def get_orderbook(self, token_id: str, depth: int = 100) -> OrderBook:
        """Get order book for a token.

        Args:
            token_id: Token ID (outcome token identifier)
            depth: Number of price levels to return (default: 100)

        Returns:
            OrderBook object containing bids and asks

        Raises:
            PolymarketAPIError: If the API request fails
            PolymarketValidationError: If token_id is invalid

        Example:
            >>> ob = client.get_orderbook("1234567890abcdef")
            >>> print(f"Best bid: {ob.best_bid}, Best ask: {ob.best_ask}")
            >>> print(f"Mid price: {ob.mid_price}")
        """
        if not token_id or not isinstance(token_id, str):
            raise PolymarketValidationError("Token ID must be a non-empty string")

        if depth < 1 or depth > 1000:
            raise PolymarketValidationError("Depth must be between 1 and 1000")

        try:
            # Use CLOB API for order book
            params = {"depth": depth} if depth != 100 else {}

            data = self._make_request(
                "GET",
                f"/book/{token_id}",
                base_url=self.api_url,
                params=params if params else None
            )

            orderbook = OrderBook.from_api_response(token_id, data)
            logger.debug(
                f"Orderbook for {token_id}: "
                f"{len(orderbook.bids)} bids, {len(orderbook.asks)} asks"
            )
            return orderbook

        except PolymarketAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get orderbook for token {token_id}: {e}")
            raise PolymarketAPIError(f"Failed to get orderbook: {str(e)}") from e

    def get_prices(self, market_id: str) -> Dict[str, float]:
        """Get current prices for a market.

        Retrieves current market prices for all outcomes in a market.
        Prices are normalized to be between 0 and 1.

        Args:
            market_id: Market ID or slug

        Returns:
            Dictionary mapping outcome names to prices (0.0 to 1.0)

        Raises:
            PolymarketAPIError: If the API request fails
            PolymarketValidationError: If market_id is invalid

        Example:
            >>> prices = client.get_prices("will-bitcoin-hit-100k")
            >>> for outcome, price in prices.items():
            ...     print(f"{outcome}: ${price:.2%}")
        """
        if not market_id or not isinstance(market_id, str):
            raise PolymarketValidationError("Market ID must be a non-empty string")

        try:
            # Get market data from Gamma API
            data = self._make_request(
                "GET",
                f"/markets/{market_id}",
                base_url=self.gamma_api_url
            )

            prices = {}

            # Parse outcome prices
            outcomes = data.get("outcomes", [])
            outcome_prices = data.get("outcomePrices", data.get("outcome_prices", {}))

            if isinstance(outcomes, list):
                for outcome in outcomes:
                    if isinstance(outcome, dict):
                        name = outcome.get("name", "")
                    else:
                        name = str(outcome)

                    if name and name in outcome_prices:
                        try:
                            price = outcome_prices[name]
                            if isinstance(price, str):
                                prices[name] = float(price)
                            elif isinstance(price, (int, float)):
                                prices[name] = float(price)
                        except (ValueError, TypeError):
                            continue

            # Try to get additional prices from orderbooks
            if isinstance(outcomes, list):
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue

                    name = outcome.get("name", "")
                    token_id = outcome.get("clobTokenId") or outcome.get("token_id")

                    # Skip if we already have a price
                    if name in prices and prices[name] > 0:
                        continue

                    # Try to get price from orderbook
                    if token_id:
                        try:
                            ob = self.get_orderbook(token_id, depth=1)
                            if ob.mid_price is not None:
                                prices[name] = ob.mid_price
                        except Exception:
                            pass

            logger.debug(f"Retrieved {len(prices)} prices for market {market_id}")
            return prices

        except PolymarketAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get prices for market {market_id}: {e}")
            raise PolymarketAPIError(f"Failed to get prices: {str(e)}") from e

    # ==================== Account Methods ====================

    def get_balance(self) -> Balance:
        """Get account balance.

        Retrieves the current USDC balance and trading allowance.
        Requires authentication with a private key.

        Returns:
            Balance object with USDC and optional WETH balances

        Raises:
            PolymarketAPIError: If the API request fails
            PolymarketAuthError: If authentication fails or no private key

        Example:
            >>> balance = client.get_balance()
            >>> print(f"Available: {balance.usdc_balance:.2f} USDC")
            >>> print(f"Allowance: {balance.usdc_allowance:.2f} USDC")
        """
        if not self.clob_client:
            raise PolymarketAuthError(
                "Private key required for balance queries. "
                "Initialize with private_key parameter."
            )

        try:
            # Try py-clob-client first
            if hasattr(self.clob_client, 'get_balance'):
                balance_data = self.clob_client.get_balance()
                balance = Balance.from_api_response(balance_data)
                logger.info(
                    f"Balance retrieved: {balance.usdc_balance:.2f} USDC "
                    f"(allowance: {balance.usdc_allowance:.2f})"
                )
                return balance

            # Fallback to API call
            data = self._make_request(
                "GET",
                "/account/balance",
                base_url=self.api_url
            )

            balance = Balance.from_api_response(data)
            logger.info(
                f"Balance retrieved: {balance.usdc_balance:.2f} USDC"
            )
            return balance

        except PolymarketAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            raise PolymarketAPIError(f"Failed to get balance: {str(e)}") from e

    def get_positions(
        self,
        market_id: Optional[str] = None,
        include_closed: bool = False
    ) -> List[Position]:
        """Get current positions.

        Retrieves all current trading positions. Requires authentication.

        Args:
            market_id: Optional market ID to filter positions
            include_closed: Include closed positions (default: False)

        Returns:
            List of Position objects

        Raises:
            PolymarketAPIError: If the API request fails
            PolymarketAuthError: If authentication fails

        Example:
            >>> positions = client.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.outcome}: {pos.quantity} @ ${pos.avg_buy_price:.3f}")
            ...     if pos.unrealized_pnl:
            ...         print(f"  PnL: ${pos.unrealized_pnl:.2f}")
        """
        if not self.clob_client and not self.api_key:
            raise PolymarketAuthError(
                "Private key or API key required for position queries."
            )

        try:
            positions = []

            # Try py-clob-client first
            if self.clob_client and hasattr(self.clob_client, 'get_positions'):
                raw_positions = self.clob_client.get_positions()

                # Apply filters
                if market_id:
                    raw_positions = [
                        p for p in raw_positions
                        if p.get("market_id") == market_id
                        or p.get("condition_id") == market_id
                    ]

                if not include_closed:
                    raw_positions = [
                        p for p in raw_positions
                        if float(p.get("quantity", 0) or p.get("size", 0)) != 0
                    ]

                positions = [Position.from_api_response(p) for p in raw_positions]
            else:
                # Fallback to API
                params: Dict[str, Any] = {}
                if market_id:
                    params["market_id"] = market_id
                if not include_closed:
                    params["status"] = "open"

                data = self._make_request(
                    "GET",
                    "/positions",
                    base_url=self.api_url,
                    params=params if params else None
                )

                # Parse response
                if isinstance(data, dict):
                    raw_positions = data.get("positions", data.get("data", []))
                elif isinstance(data, list):
                    raw_positions = data
                else:
                    raw_positions = []

                if not isinstance(raw_positions, list):
                    raw_positions = []

                positions = [Position.from_api_response(p) for p in raw_positions]

            logger.info(f"Retrieved {len(positions)} positions")
            return positions

        except PolymarketAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise PolymarketAPIError(f"Failed to get positions: {str(e)}") from e

    # ==================== Utility Methods ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get client usage statistics.

        Returns:
            Dictionary with statistics including:
            - api_calls: Total API calls made
            - errors: Total errors encountered
            - retries: Total retries performed
        """
        return {
            "api_calls": self._api_calls,
            "errors": self._errors,
            "retries": self._retries,
            "clob_client_available": self.clob_client is not None,
        }

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._api_calls = 0
        self._errors = 0
        self._retries = 0
        logger.debug("Statistics reset")

    def close(self) -> None:
        """Close the client session.

        Releases all resources and closes network connections.
        Should be called when done using the client, or use as context manager.

        Example:
            >>> client = PolymarketClient()
            >>> try:
            ...     markets = client.get_markets()
            ... finally:
            ...     client.close()
        """
        if self.session:
            self.session.close()
            logger.info("PolymarketClient session closed")

    def __enter__(self):
        """Context manager entry.

        Returns:
            Self for use in with statement
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit.

        Ensures session is closed even if an exception occurs.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value
            exc_tb: Exception traceback

        Returns:
            False to not suppress exceptions
        """
        self.close()
        return False

    def __repr__(self) -> str:
        """String representation of the client."""
        return (
            f"PolymarketClient("
            f"api_url='{self.api_url}', "
            f"proxy='{self.proxy}', "
            f"clob={'connected' if self.clob_client else 'not connected'}, "
            f"calls={self._api_calls}, "
            f"errors={self._errors}"
            f")"
        )


# ==================== Convenience Functions ====================

def create_client(
    private_key: Optional[str] = None,
    api_url: Optional[str] = None,
    proxy: Optional[str] = None,
    **kwargs
) -> PolymarketClient:
    """Create a PolymarketClient with sensible defaults.

    This is a convenience function for quickly creating a client
    without specifying all parameters.

    Args:
        private_key: Ethereum private key (0x...)
        api_url: Custom API URL (default: https://clob.polymarket.com)
        proxy: Proxy URL (default: http://127.0.0.1:7890)
        **kwargs: Additional arguments for PolymarketClient

    Returns:
        Configured PolymarketClient instance

    Example:
        >>> # Basic usage for public data
        >>> client = create_client()
        >>> markets = client.get_markets(limit=5)

        >>> # With private key for authenticated requests
        >>> client = create_client(private_key="0x...")
        >>> balance = client.get_balance()
    """
    return PolymarketClient(
        private_key=private_key,
        api_url=api_url,
        proxy=proxy,
        **kwargs
    )


def get_client_from_env() -> PolymarketClient:
    """Create a PolymarketClient from environment variables.

    Reads configuration from environment variables:
    - POLYMARKET_PRIVATE_KEY: Ethereum private key
    - POLYMARKET_API_URL: API URL (default: https://clob.polymarket.com)
    - POLYMARKET_PROXY: Proxy URL (default: http://127.0.0.1:7890)
    - POLYMARKET_API_KEY: Optional API key
    - POLYMARKET_SECRET: Optional API secret

    Returns:
        Configured PolymarketClient instance

    Raises:
        PolymarketValidationError: If required env vars are missing

    Example:
        >>> # Set env vars first:
        >>> # export POLYMARKET_PRIVATE_KEY=0x...
        >>>
        >>> client = get_client_from_env()
        >>> print(client.get_balance())
    """
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    api_url = os.getenv("POLYMARKET_API_URL")
    proxy = os.getenv("POLYMARKET_PROXY")
    api_key = os.getenv("POLYMARKET_API_KEY")
    secret = os.getenv("POLYMARKET_SECRET")
    passphrase = os.getenv("POLYMARKET_PASSPHRASE")

    return PolymarketClient(
        private_key=private_key,
        api_url=api_url,
        proxy=proxy,
        api_key=api_key,
        secret=secret,
        passphrase=passphrase
    )


# ==================== Main Entry Point ====================

if __name__ == "__main__":
    # Simple demo/test when run directly
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=" * 60)
    print("PolymarketClient Demo")
    print("=" * 60)

    # Create client without private key for public data access
    client = PolymarketClient()

    try:
        # Get markets
        print("\n1. Fetching markets...")
        markets = client.get_markets(limit=5)
        print(f"   Retrieved {len(markets)} markets:")

        for i, market in enumerate(markets[:3], 1):
            print(f"   {i}. {market.question[:50]}...")
            print(f"      Volume: ${market.volume:,.0f} | Status: {market.status}")

        if markets:
            # Get order book for first market's first outcome
            market = markets[0]
            if market.outcomes:
                token_id = None
                outcome_name = "Unknown"

                for outcome in market.outcomes:
                    if isinstance(outcome, dict):
                        token_id = outcome.get("clob_token_id") or outcome.get("token_id")
                        outcome_name = outcome.get("name", "Unknown")
                        if token_id:
                            break

                if token_id:
                    print(f"\n2. Fetching order book for: {outcome_name[:30]}...")
                    ob = client.get_orderbook(token_id, depth=5)
                    print(f"   Best bid: {ob.best_bid}")
                    print(f"   Best ask: {ob.best_ask}")
                    print(f"   Mid price: {ob.mid_price}")
                    print(f"   Bids: {len(ob.bids)}, Asks: {len(ob.asks)}")

            # Get prices for the market
            print(f"\n3. Fetching prices for: {market.question[:40]}...")
            prices = client.get_prices(market.id)
            print(f"   Retrieved {len(prices)} prices:")
            for outcome, price in list(prices.items())[:3]:
                print(f"   - {outcome}: {price:.2%}")

        # Display statistics
        print(f"\n4. Client Statistics:")
        stats = client.get_stats()
        print(f"   API calls: {stats['api_calls']}")
        print(f"   Errors: {stats['errors']}")
        print(f"   CLOB client: {'connected' if stats['clob_client_available'] else 'not connected'}")

        print("\n" + "=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)

    except PolymarketAuthError as e:
        print(f"\nAuthentication error: {e}")
        print("Note: Some features require a private key")
    except PolymarketAPIError as e:
        print(f"\nAPI error: {e}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        logger.exception("Demo failed")
    finally:
        client.close()
        print("\nClient session closed.")
