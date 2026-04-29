"""Strategy runner service for scheduled execution."""

import asyncio
import concurrent.futures
import json
import logging
import sys
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure proxy env vars are set before py_clob_client imports its httpx.Client
_proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
if _proxy_url:
    if not os.environ.get("HTTP_PROXY"):
        os.environ["HTTP_PROXY"] = _proxy_url
    if not os.environ.get("HTTPS_PROXY"):
        os.environ["HTTPS_PROXY"] = _proxy_url

logger = logging.getLogger("worker.strategy")

# strategy_exec logger configured by setup_logging("worker") in worker.py
strategy_exec_logger = logging.getLogger("strategy_exec")

# Ensure strategy-py is importable
_backend_py_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_project_root = os.path.dirname(_backend_py_dir)
_strategy_py_src = os.path.join(_project_root, "strategy-py", "src")
if _strategy_py_src not in sys.path:
    sys.path.insert(0, _strategy_py_src)

from src.database import AsyncSessionLocal
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.wallet import Wallet
from src.models.signal_log import SignalLog
from src.models.order import Order
from src.models.position import Position
from src.models.provider import Provider
from src.services.data_source_manager import get_data_source_manager, DataSource, SignalFilter, TriggerChecker, MarketData, ActivityData
from src.core.crypto import decrypt_private_key

# Import factor strategy from strategy-py
from strategy.buy_strategy import (
    BuyStrategy,
    BuyStrategyConfig,
    MarketContext as BuyMarketContext,
    OddsBiasMetrics,
    TimeDecayMetrics,
    OrderbookPressureMetrics,
    CapitalFlowMetrics,
    SportsMomentumMetrics,
    BuyDecision,
    BuyDecisionOutput,
)
from strategy.capital_flow_analyzer import (
    CapitalFlowAssistedExit,
    DecisionAction,
)
from strategy.entry_condition import EntryConditionValidator, EntryConditionConfig
from src.trading_engine.expiry_policy import ExpiryPolicy, ExpiryAction


class _EntryConditionAdapter:
    """Lightweight adapter to feed MarketData into EntryConditionValidator.

    EntryConditionValidator requires MarketInfoSource, LiquiditySource,
    and VolatilitySource protocol implementations. This adapter wraps
    a MarketData object so the validator can run its checks without
    additional async I/O.
    """

    def __init__(self, market_data: MarketData, market_dict: Optional[Dict[str, Any]] = None):
        self._md = market_data
        self._market_dict = market_dict or {}

    def get_market_info(self, market_id: str) -> Dict[str, Any]:
        return {
            "current_price": self._md.yes_price,
            "last_price": self._md.yes_price,
            "token_id": self._md.token_id,
            "volume": self._md.volume,
        }

    def get_market_expiry(self, market_id: str) -> Optional[datetime]:
        if self._md.hours_to_expiry and self._md.hours_to_expiry > 0:
            return datetime.now() + timedelta(hours=self._md.hours_to_expiry)
        return None

    def get_market_category(self, market_id: str) -> Optional[str]:
        return None

    def get_available_liquidity(self, market_id: str) -> float:
        # Prefer actual liquidity from Gamma API market metadata
        liquidity = self._market_dict.get("liquidity")
        if liquidity is not None:
            return float(liquidity)
        # Fallback to volume (though volume != liquidity)
        return self._md.volume or 0.0

    def get_order_book_depth(self, market_id: str) -> Dict[str, float]:
        return {"bid": 0.0, "ask": 0.0}

    def get_volatility(self, market_id: str, period: str = "24h") -> float:
        # 1. Prefer WebSocket change_24h if available
        change = self._md.change_24h
        if change:
            return abs(change)

        # 2. Fallback: infer activity from Gamma API 24h volume.
        #    Polymarket Market Channel WebSocket does not provide change_24h,
        #    but high volume24hr implies price movement / market activity.
        vol24 = (
            self._market_dict.get("volume24hr")
            or self._market_dict.get("volume24hrClob")
            or self._market_dict.get("volume")
            or 0
        )
        try:
            vol24 = float(vol24)
        except (ValueError, TypeError):
            vol24 = 0.0

        # DEBUG: log when fallback is used
        if vol24 == 0:
            strategy_exec_logger.debug(
                "[VOL_DEBUG] market_id=%s vol24=%s market_keys=%s",
                market_id,
                self._market_dict.get("volume24hr"),
                [k for k in self._market_dict.keys() if "volume" in k.lower() or "liquid" in k.lower()],
            )

        if vol24 >= 5000:
            return 0.08
        elif vol24 >= 1000:
            return 0.05
        elif vol24 >= 100:
            return 0.02

        return 0.0

    def get_price_range(self, market_id: str, period: str = "24h") -> Tuple[float, float]:
        p = self._md.yes_price
        return (p * 0.95, p * 1.05)


class StrategyRunner:
    """Strategy execution runner with factor-based decision and position monitoring."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._data_source_manager = get_data_source_manager()
        self.clob_client: Optional["ClobClient"] = None  # py-clob-client v2

        # Global proxy for all HTTP requests
        self._proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
        self._http_client = httpx.AsyncClient(
            proxy=self._proxy_url,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(15.0, connect=10.0),
        )

        # Market cache refresh tracking
        self._last_cache_refresh: Optional[datetime] = None
        self._market_cache_refresh_interval = 600  # 10 minutes

        # Factor strategy engine
        self._buy_strategy: Optional[BuyStrategy] = None

        # Position exit assistant (stop-loss / take-profit with capital flow)
        self._flow_exit = CapitalFlowAssistedExit(
            config={"enabled": True},
            decision_config={
                "weights": {"price_based_exit": 0.7, "flow_acceleration": 0.3},
                "confidence_threshold": 0.6,
                "enable_extreme_override": True,
            },
        )

        # Market data cache (condition_id -> market dict)
        self._market_cache: Dict[str, dict] = {}
        self._market_cache_ttl: Optional[datetime] = None
        self._market_cache_duration_seconds = 300  # 5 minutes - reduces API pressure while staying fresh

        # Token ID -> Condition ID mapping (for quick lookup)
        self._token_to_condition: Dict[str, str] = {}

        # Condition ID -> (yes_token_id, no_token_id) mapping
        self._condition_to_tokens: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

        # File-based persistent cache
        self._cache_dir = Path(__file__).parent.parent.parent / "data"
        self._cache_file = self._cache_dir / "market_cache.json"
        self._cache_ttl_hours = 24
        self._markets_added_since_save = 0
        self._auto_save_threshold = 100

        # Load persistent cache at startup (if available and not expired)
        self._load_market_cache()

        # Trigger checkers per strategy (persist cooldown state across iterations)
        self._trigger_checkers: Dict[UUID, TriggerChecker] = {}

        # Hot market handler references per strategy (for unregister on stop)
        self._hot_market_handlers: Dict[UUID, Callable] = {}

        # Provider cache to avoid repeated DB queries for AI analysis
        self._provider_cache: Dict[UUID, Optional[dict]] = {}

        # Run-once requests from API (supervisor pushes, loop consumes)
        self._run_once_requests: set[UUID] = set()

        # Concurrency control to avoid starving the event loop
        self._eval_semaphore = asyncio.Semaphore(15)
        self._ai_semaphore = asyncio.Semaphore(3)  # limit AI API concurrency
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="strategy_"
        )

        # Lightweight evaluation stats (reset on summary print)
        self._eval_stats: Dict[str, int] = {
            "total": 0,
            "data_source_unhealthy": 0,
            "no_market": 0,
            "no_price": 0,
            "signal_filter": 0,
            "keyword_filter": 0,
            "entry_condition": 0,
            "factor_rejected": 0,
            "ai_none": 0,
            "signal": 0,
            "order_failed": 0,
            "order_ok": 0,
        }
        self._last_summary_at: float = 0.0

    def _record_eval(self, reason: str) -> None:
        """Increment evaluation outcome counter."""
        self._eval_stats["total"] += 1
        self._eval_stats[reason] = self._eval_stats.get(reason, 0) + 1

    def _log_summary(self) -> None:
        """Print a one-line summary of evaluation stats since last call."""
        now = time.time()
        if now - self._last_summary_at < 30:
            return
        self._last_summary_at = now
        s = self._eval_stats
        if s["total"] == 0:
            strategy_exec_logger.info("[SUMMARY] no evaluations in last 30s")
            return
        parts = [
            f"eval={s['total']}",
            f"signal={s['signal']}",
            f"ordered={s['order_ok']}",
            f"no_market={s['no_market']}",
            f"no_price={s['no_price']}",
            f"filter={s['signal_filter']}",
            f"entry={s['entry_condition']}",
            f"factor={s['factor_rejected']}",
            f"ai_none={s['ai_none']}",
            f"unhealthy={s['data_source_unhealthy']}",
        ]
        strategy_exec_logger.info("[SUMMARY] %s", " | ".join(parts))
        # Reset counters
        for k in s:
            s[k] = 0

    def _get_cached_markets(self) -> List[dict]:
        """Return cached markets if not expired (deduplicated by object identity)."""
        if self._market_cache_ttl and datetime.now(timezone.utc) < self._market_cache_ttl:
            # Deduplicate: same market dict may be cached under both hex and numeric keys
            seen: set = set()
            result: List[dict] = []
            for m in self._market_cache.values():
                mid = id(m)
                if mid not in seen:
                    seen.add(mid)
                    result.append(m)
            return result
        return []

    def _cache_markets(self, markets: List[dict], incremental: bool = False) -> None:
        """Cache markets and build token->condition mapping.

        Args:
            markets: list of market dicts from Gamma API
            incremental: if True, merge into existing cache instead of clearing
        """
        if not incremental:
            self._market_cache.clear()
            self._token_to_condition.clear()
            self._condition_to_tokens.clear()

        for m in markets:
            hex_id = m.get("conditionId") or m.get("condition_id")
            numeric_id = m.get("id")

            if not hex_id and not numeric_id:
                continue

            cache_key = hex_id or str(numeric_id)
            is_new = cache_key not in self._market_cache
            if incremental and cache_key in self._market_cache:
                # Merge: preserve existing fields not present in new dict
                # (prevents hot-market simplified dict from overwriting full Gamma API data)
                existing = self._market_cache[cache_key]
                merged = {**existing, **m}
                self._market_cache[cache_key] = merged
                if hex_id and numeric_id:
                    self._market_cache[str(numeric_id)] = merged
            else:
                self._market_cache[cache_key] = m
                if hex_id and numeric_id:
                    self._market_cache[str(numeric_id)] = m

            map_key = hex_id or str(numeric_id)

            # Build token -> condition mapping
            for token in m.get("tokens", []):
                tid = token.get("token_id") or token.get("clobTokenId", "")
                if tid:
                    self._token_to_condition[tid] = map_key
            clob_ids = m.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                for side, tid in clob_ids.items():
                    if tid:
                        self._token_to_condition[tid] = map_key

            # Build condition -> (yes, no) tokens mapping from clobTokenIds
            raw_clob = m.get("clobTokenIds")
            if raw_clob:
                try:
                    if isinstance(raw_clob, str):
                        clob_list = json.loads(raw_clob)
                    elif isinstance(raw_clob, list):
                        clob_list = raw_clob
                    else:
                        clob_list = []
                    if len(clob_list) >= 2:
                        self._condition_to_tokens[map_key] = (clob_list[0], clob_list[1])
                        # Also build reverse mapping token_id -> condition_id
                        for tid in clob_list:
                            if tid:
                                self._token_to_condition[str(tid)] = map_key
                except Exception:
                    pass
            elif m.get("tokens"):
                yes_tid = None
                no_tid = None
                for token in m.get("tokens", []):
                    outcome = (token.get("outcome") or "").lower()
                    tid = token.get("token_id") or token.get("clobTokenId", "")
                    if outcome in ("yes", "y"):
                        yes_tid = tid
                    elif outcome in ("no", "n"):
                        no_tid = tid
                if yes_tid or no_tid:
                    self._condition_to_tokens[map_key] = (yes_tid, no_tid)

            if is_new:
                self._markets_added_since_save += 1

        self._market_cache_ttl = datetime.now(timezone.utc) + timedelta(
            seconds=self._market_cache_duration_seconds
        )
        unique_count = len({id(m) for m in self._market_cache.values()})
        logger.info(
            "Markets cached: %d unique markets (%d keys), %d token mappings, %d condition->token pairs",
            unique_count, len(self._market_cache), len(self._token_to_condition),
            len(self._condition_to_tokens),
        )

    def _save_market_cache(self) -> None:
        """Persist market cache to disk (atomic write with backup)."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "version": "1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "markets": list(self._market_cache.values()),
                "condition_to_tokens": {
                    k: list(v) for k, v in self._condition_to_tokens.items()
                },
                "token_to_condition": self._token_to_condition,
            }
            temp_file = self._cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            if self._cache_file.exists():
                backup = self._cache_file.with_suffix(".bak")
                if backup.exists():
                    backup.unlink()
                self._cache_file.rename(backup)
            temp_file.rename(self._cache_file)
            logger.info("[CACHE] Saved %d markets to %s", len(self._market_cache), self._cache_file)
            self._markets_added_since_save = 0
        except Exception as e:
            logger.warning("[CACHE] Failed to save market cache: %s", e)

    def _load_market_cache(self) -> bool:
        """Load market cache from disk (with backup recovery)."""
        for file_path, label in [(self._cache_file, "main"), (self._cache_file.with_suffix(".bak"), "backup")]:
            try:
                if not file_path.exists():
                    continue
                with open(file_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                if cache_data.get("version") != "1.0":
                    continue
                ts = cache_data.get("timestamp", "")
                if ts:
                    try:
                        cached_at = datetime.fromisoformat(ts)
                        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
                        if age_hours > self._cache_ttl_hours:
                            logger.info("[CACHE] %s cache expired (%.1fh old), skipping", label, age_hours)
                            continue
                    except Exception:
                        pass
                markets = cache_data.get("markets", [])
                self._cache_markets(markets, incremental=False)
                # Restore condition_to_tokens
                ctt = cache_data.get("condition_to_tokens", {})
                for k, v in ctt.items():
                    if isinstance(v, list) and len(v) >= 2:
                        self._condition_to_tokens[k] = (v[0], v[1])
                # Restore token_to_condition
                ttc = cache_data.get("token_to_condition", {})
                self._token_to_condition.update(ttc)
                logger.info("[CACHE] Loaded %d markets from %s cache", len(markets), label)
                return True
            except Exception as e:
                logger.warning("[CACHE] Failed to load %s cache: %s", label, e)
        return False

    async def _refresh_market_cache(self, data_source: DataSource) -> None:
        """批量获取活跃市场列表并增量更新 runner + data_source 缓存。

        使用 incremental=True 合并到现有缓存，保留文件缓存和 WebSocket
        活动中已积累的 token 映射，避免数据丢失。
        """
        try:
            all_markets: List[dict] = []
            offset = 0
            page_limit = 1000
            max_pages = 10  # safety cap: 10k markets
            async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                for page in range(max_pages):
                    resp = await client.get(
                        "https://gamma-api.polymarket.com/markets",
                        params={
                            "active": "true",
                            "closed": "false",
                            "limit": page_limit,
                            "offset": offset,
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    page_markets = data if isinstance(data, list) else data.get("markets", [])
                    if not page_markets:
                        break
                    all_markets.extend(page_markets)
                    if len(page_markets) < page_limit:
                        break
                    offset += page_limit

            markets = all_markets

            # Merge token details from WebSocket activity feed for markets lacking them
            activity_tokens: Dict[str, str] = {}
            if hasattr(data_source, "get_condition_token_map"):
                activity_tokens = data_source.get_condition_token_map()

            for m in markets:
                cid = m.get("conditionId") or m.get("condition_id") or m.get("id", "")
                if not cid:
                    continue
                if not m.get("tokens"):
                    # Prefer existing cache tokens, then activity feed
                    existing = self._market_cache.get(cid, {})
                    if existing.get("tokens"):
                        m["tokens"] = existing["tokens"]
                    elif cid in activity_tokens:
                        m["tokens"] = [{"token_id": activity_tokens[cid], "outcome": "Yes"}]

            # Incremental merge: preserves existing mappings and only adds/updates
            self._cache_markets(markets, incremental=True)

            # Push metadata into data_source so _get_hours_to_expiry works
            if hasattr(data_source, "update_market_meta"):
                for m in markets:
                    tid = self._get_market_yes_token_id(m)
                    if tid:
                        data_source.update_market_meta(tid, m)

            self._last_cache_refresh = datetime.now(timezone.utc)
            logger.info("Market cache refreshed: %d markets (incremental)", len(markets))

            # Auto-save if enough new markets accumulated
            if self._markets_added_since_save >= self._auto_save_threshold:
                self._save_market_cache()
        except Exception as e:
            logger.warning("Failed to refresh market cache: %s", e)

    def _get_market_yes_token_id(self, market: dict) -> Optional[str]:
        """Extract YES/Up token_id from Gamma market dict for CLOB price lookup.

        Gamma API returns condition_id in 'id' field and CLOB token_ids in
        'tokens' or 'clob_token_ids'. We need the actual CLOB token_id for
        PriceMonitor subscription and lookup.
        """
        if not market:
            return None

        # Try clob_token_ids dict first
        clob_ids = market.get("clob_token_ids", {})
        if isinstance(clob_ids, dict):
            for key, tid in clob_ids.items():
                if key.lower() in ("yes", "y") and tid:
                    return tid

        # Fall back to tokens list (supports Yes/Up and other primary outcomes)
        tokens = market.get("tokens", [])
        for token in tokens:
            outcome = token.get("outcome", "")
            if outcome and outcome.lower() in ("yes", "y", "up"):
                tid = token.get("token_id") or token.get("clobTokenId", "")
                if tid:
                    return tid

        # Debug: log unmatched tokens
        if tokens:
            strategy_exec_logger.info("[TOKEN] no yes-match in tokens: %s", tokens)
            # Fallback: for binary markets with exactly 2 tokens, first is usually Yes
            if len(tokens) == 2:
                tid = tokens[0].get("token_id") or tokens[0].get("clobTokenId", "")
                if tid:
                    strategy_exec_logger.info("[TOKEN] using first token as yes fallback: %s", tid)
                    return tid
            # If only one token, use it
            if len(tokens) == 1:
                tid = tokens[0].get("token_id") or tokens[0].get("clobTokenId", "")
                if tid:
                    return tid

        return None

    def _get_market_no_token_id(self, market: dict) -> Optional[str]:
        """Extract NO/Down token_id from Gamma market dict (synchronous, no HTTP)."""
        if not market:
            return None

        # Try clob_token_ids dict first
        clob_ids = market.get("clob_token_ids", {})
        if isinstance(clob_ids, dict):
            for key, tid in clob_ids.items():
                if key.lower() in ("no", "n", "down") and tid:
                    return tid

        # Fall back to tokens list
        tokens = market.get("tokens", [])
        for token in tokens:
            outcome = token.get("outcome", "")
            if outcome and outcome.lower() in ("no", "n", "down"):
                tid = token.get("token_id") or token.get("clobTokenId", "")
                if tid:
                    return tid

        # Fallback: for binary markets with exactly 2 tokens, pick the non-yes one
        if len(tokens) == 2:
            yes_tid = self._get_market_yes_token_id(market)
            tid0 = tokens[0].get("token_id") or tokens[0].get("clobTokenId", "")
            tid1 = tokens[1].get("token_id") or tokens[1].get("clobTokenId", "")
            if yes_tid and tid0 and tid1:
                return tid1 if yes_tid == tid0 else tid0

        return None

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        logger.info("Strategy %s: start requested", strategy_id)
        if strategy_id in self._tasks:
            existing_task = self._tasks[strategy_id]
            if not existing_task.done() and not existing_task.cancelled():
                logger.info("Strategy %s: already running, skip", strategy_id)
                return  # Already running
            # Clean up finished/cancelled task so we can restart
            del self._tasks[strategy_id]
            logger.info("Strategy %s: cleaned up stale task reference", strategy_id)

        # Get strategy and portfolio info from database
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()
            if not strategy:
                raise ValueError("Strategy not found")
            if not strategy.portfolio_id:
                raise ValueError("Strategy has no portfolio assigned")
            logger.info("Strategy %s: loaded strategy '%s' for portfolio %s", strategy_id, strategy.name, strategy.portfolio_id)

            # Initialize ClobClient v2 if not already done
            if not self.clob_client:
                logger.info("Strategy %s: initializing ClobClient...", strategy_id)
                wallet_result = await db.execute(
                    select(Wallet)
                    .where(Wallet.user_id == strategy.user_id, Wallet.is_default == True)
                    .limit(1)
                )
                wallet = wallet_result.scalar_one_or_none()
                private_key = (
                    decrypt_private_key(wallet.private_key_encrypted)
                    if wallet and wallet.private_key_encrypted
                    else None
                )
                proxy = wallet.proxy_wallet_address if wallet else None
                logger.info("Strategy %s: default wallet found=%s, has_private_key=%s, proxy=%s", strategy_id, wallet is not None, private_key is not None, proxy is not None)

                if not private_key:
                    logger.warning(
                        "Strategy %s: No default wallet with private key found, "
                        "running in monitoring-only mode (no auto-trading)",
                        strategy_id,
                    )
                else:
                    try:
                        from py_clob_client_v2 import ClobClient

                        kwargs = {
                            "host": "https://clob.polymarket.com",
                            "chain_id": 137,
                            "key": private_key,
                        }
                        if proxy:
                            kwargs["signature_type"] = 2
                            kwargs["funder"] = proxy

                        self.clob_client = ClobClient(**kwargs)
                        creds = self.clob_client.create_or_derive_api_key()
                        self.clob_client.set_api_creds(creds)
                        logger.info("Strategy %s: ClobClient v2 initialized successfully", strategy_id)
                    except Exception as e:
                        logger.error("Strategy %s: Failed to initialize ClobClient: %s", strategy_id, e)
                        raise

        # Get or create shared data source (starts WebSocket connections)
        logger.info("Strategy %s: creating data source for portfolio %s...", strategy_id, strategy.portfolio_id)
        try:
            data_source = await self._data_source_manager.get_or_create_source(
                portfolio_id=strategy.portfolio_id,
                source_type="polymarket"
            )
        except Exception as e:
            logger.error("Strategy %s: DataSource creation failed: %s", strategy_id, e)
            raise

        # Register event-driven hot market handler (significant capital flow triggers evaluation)
        if hasattr(data_source, "register_hot_market_handler"):
            hot_handler = lambda cid, wd: asyncio.create_task(
                self._on_hot_market(strategy_id, cid, wd)
            )
            self._hot_market_handlers[strategy_id] = hot_handler
            data_source.register_hot_market_handler(hot_handler)
            logger.info("Strategy %s: registered hot market handler", strategy_id)

        task = asyncio.create_task(self._run_strategy_loop(strategy_id, data_source))
        self._tasks[strategy_id] = task
        logger.info("Strategy %s: loop task created and registered", strategy_id)

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]
            self._trigger_checkers.pop(strategy_id, None)

        # Unregister hot market handler
        handler = self._hot_market_handlers.pop(strategy_id, None)
        if handler:
            for source in await self._data_source_manager.get_all_sources():
                if hasattr(source, "unregister_hot_market_handler"):
                    source.unregister_hot_market_handler(handler)
            logger.info("Strategy %s: unregistered hot market handler", strategy_id)

        logger.info("Strategy %s: stopped", strategy_id)

    def request_run_once(self, strategy_id: UUID) -> None:
        """Run-once is disabled in event-driven mode; signals only come from WebSocket events."""
        logger.info("Strategy %s: run-once ignored (event-driven mode)", strategy_id)

    async def _run_strategy_loop(self, strategy_id: UUID, data_source: DataSource) -> None:
        """Main strategy execution loop."""
        try:
            # Load strategy once
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()

            if not strategy:
                logger.warning("Strategy %s: not found in DB, exiting loop", strategy_id)
                return

            interval = 60  # 1min loop: position sync + subscribe only, no polling scan
            iteration = 0
            strategy_exec_logger.info("[START] Strategy %s (%s) loop started, interval=%ds, is_active=%s, is_paused=%s (event-driven only)",
                                      strategy_id, strategy.name, interval, strategy.is_active, strategy.is_paused)

            # Warm-up (with its own session)
            try:
                async with AsyncSessionLocal() as db:
                    onchain_positions = await self._sync_onchain_positions(db, strategy)
                    strategy_exec_logger.info("[WARMUP] on-chain positions: %d", len(onchain_positions))
                    onchain_token_ids = [p["token_id"] for p in onchain_positions if p.get("token_id")]
                    if onchain_token_ids and hasattr(data_source, "subscribe"):
                        await data_source.subscribe(onchain_token_ids)
                        strategy_exec_logger.info("[WARMUP] subscribed %d on-chain tokens", len(onchain_token_ids))

                    markets = await self._get_available_markets(strategy, data_source)
                    strategy_exec_logger.info("[WARMUP] fetched %d markets", len(markets))
                    if markets:
                        warm_token_ids: List[str] = []
                        for m in markets:
                            cid = m.get("id") or m.get("conditionId") or m.get("condition_id", "")
                            tid = self._get_market_yes_token_id(m)
                            if cid and tid:
                                warm_token_ids.append(tid)
                                self._token_to_condition[tid] = cid
                        if warm_token_ids and hasattr(data_source, "subscribe"):
                            await data_source.subscribe(warm_token_ids)
                            strategy_exec_logger.info("[WARMUP] subscribed %d market tokens", len(warm_token_ids))
            except Exception as e:
                strategy_exec_logger.error("[WARMUP] failed: %s", e)

            while True:
                try:
                    # Reload strategy state each iteration (outside long-lived session)
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Strategy).where(Strategy.id == strategy_id)
                        )
                        strategy = result.scalar_one_or_none()
                        if not strategy or not strategy.is_active:
                            strategy_exec_logger.info("[EXIT] strategy %s inactive or deleted", strategy_id)
                            break
                except Exception as e:
                    strategy_exec_logger.error("[ITER] strategy reload failed: %s", e)
                    await asyncio.sleep(5)
                    continue

                iteration += 1
                strategy_exec_logger.info("[ITER] %d started for strategy %s (event-driven only, no polling)", iteration, strategy_id)

                # Refresh market cache every 10 minutes
                if (
                    self._last_cache_refresh is None
                    or (datetime.now(timezone.utc) - self._last_cache_refresh).total_seconds()
                    > self._market_cache_refresh_interval
                ):
                    await self._refresh_market_cache(data_source)

                if strategy.is_paused:
                    strategy_exec_logger.info("[ITER] strategy %s paused, skip sync", strategy_id)
                else:
                    try:
                        async with AsyncSessionLocal() as db:
                            # Subscribe WebSocket for open positions (read from DB, do NOT sync from chain here)
                            result = await db.execute(
                                select(Position).where(
                                    Position.strategy_id == strategy_id,
                                    Position.status == "open",
                                    Position.token_id.isnot(None),
                                )
                            )
                            open_positions = result.scalars().all()
                            if open_positions:
                                token_ids = [p.token_id for p in open_positions if p.token_id]
                                if token_ids and hasattr(data_source, "subscribe"):
                                    try:
                                        await data_source.subscribe(token_ids)
                                    except Exception as e:
                                        strategy_exec_logger.warning("[ITER] subscribe failed: %s", e)
                                strategy_exec_logger.info("[ITER] subscribed %d open position tokens", len(token_ids))

                            await db.commit()
                    except Exception as e:
                        strategy_exec_logger.error("[ITER] %d error: %s\n%s", iteration, e, traceback.format_exc())

                self._log_summary()
                strategy_exec_logger.info("[SLEEP] sleeping %ds (event-driven only)", interval)
                for handler in strategy_exec_logger.handlers:
                    handler.flush()
                await asyncio.sleep(interval)
                strategy_exec_logger.info("[WAKE] iteration %d resuming", iteration + 1)
        finally:
            self._tasks.pop(strategy_id, None)
            strategy_exec_logger.info("[EXIT] Strategy %s loop exited", strategy_id)

    async def _on_hot_market(
        self, strategy_id: UUID, condition_id: str, window_data: Dict[str, Any]
    ) -> None:
        """Handle significant capital flow event for a specific strategy (event-driven)."""
        event_time = window_data.get("event_time")
        if event_time:
            age = time.time() - event_time
            if age > 60:
                strategy_exec_logger.info("[HOT] event too old (%.1fs), drop %s", age, condition_id)
                return

        strategy_exec_logger.info(
            "[HOT] strategy=%s market=%s netflow=%.2f traders=%d",
            strategy_id,
            condition_id,
            window_data.get("net_flow", 0),
            window_data.get("trader_count", 0),
        )
        for handler in strategy_exec_logger.handlers:
            handler.flush()

        # Skip if strategy loop is not running
        task = self._tasks.get(strategy_id)
        if not task or task.done() or task.cancelled():
            strategy_exec_logger.info("[HOT] strategy %s not running, skip", strategy_id)
            return

        # Non-blocking acquire: drop event if semaphore is saturated
        acquired = False
        try:
            acquired = await asyncio.wait_for(self._eval_semaphore.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            strategy_exec_logger.info("[HOT] eval saturated, drop %s", condition_id)
            return

        if not acquired:
            return

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()
                if not strategy or not strategy.is_active:
                    strategy_exec_logger.info("[HOT] strategy %s inactive, skip", strategy_id)
                    return
                if strategy.is_paused:
                    strategy_exec_logger.info("[HOT] strategy %s paused, skip", strategy_id)
                    return

                data_source = await self._data_source_manager.get_or_create_source(
                    portfolio_id=strategy.portfolio_id,
                    source_type="polymarket",
                )
                if not data_source.is_healthy():
                    self._record_eval("data_source_unhealthy")
                    strategy_exec_logger.info("[HOT] unhealthy skip %s", condition_id)
                    return

                net_flow = window_data.get("net_flow", 0)
                side = "yes" if net_flow >= 0 else "no"
                trigger_data = {
                    "short_window": {**window_data, "avg_price": 0},
                    "long_window": window_data,
                }
                await self._evaluate_single_market(
                    db, strategy, data_source, condition_id, trigger_data, side=side
                )
        except Exception as e:
            strategy_exec_logger.error("[HOT] error: %s\n%s", e, traceback.format_exc())
        finally:
            self._eval_semaphore.release()

    async def _evaluate_single_market(
        self,
        db: AsyncSession,
        strategy: Strategy,
        data_source: DataSource,
        condition_id: str,
        trigger_data: Dict[str, Any],
        side: str = "yes",
    ) -> Optional[SignalLog]:
        """Evaluate a single market triggered by dual-window event (event-driven fast path).

        Args:
            side: "yes" or "no" — determined by caller based on netflow direction.
        """
        strategy_exec_logger.info("[EVAL] evaluating market %s side=%s for strategy %s", condition_id, side, strategy.id)
        for handler in strategy_exec_logger.handlers:
            handler.flush()
        _eval_start = time.time()

        # 1. Cooldown check
        trigger_checker = self._trigger_checkers.get(strategy.id)
        if trigger_checker and not trigger_checker.check_cooldown():
            strategy_exec_logger.info("[EVAL] cooldown active, skip %s", condition_id)
            return None
        t1 = time.time()

        # 2. Get market metadata and token for the chosen side
        market = self._market_cache.get(condition_id)
        if side == "yes":
            token_id = self._get_market_yes_token_id(market) if market else None
        else:
            token_id = self._get_market_no_token_id(market) if market else None

        # 2b. Cache miss: try to recover from WebSocket feed mappings first
        if not market or not token_id:
            ws_yes_tid = None
            ws_no_tid = None
            ws_meta = None
            if hasattr(data_source, "get_condition_tokens"):
                ws_yes_tid, ws_no_tid = data_source.get_condition_tokens(condition_id)
            if hasattr(data_source, "get_condition_meta"):
                ws_meta = data_source.get_condition_meta(condition_id)

            # Fallback to runner's own mapping
            if not ws_yes_tid and not ws_no_tid:
                pair = self._condition_to_tokens.get(condition_id)
                if pair:
                    ws_yes_tid, ws_no_tid = pair

            if ws_yes_tid or ws_no_tid:
                tokens = []
                if ws_yes_tid:
                    tokens.append({"token_id": ws_yes_tid, "outcome": "Yes"})
                if ws_no_tid:
                    tokens.append({"token_id": ws_no_tid, "outcome": "No"})
                # Try to get real metadata from cache first
                cached_market = self._market_cache.get(condition_id)
                # Get real-time stats from WebSocket activity feed
                ws_stats = None
                if hasattr(data_source, "get_market_stats"):
                    ws_stats = data_source.get_market_stats(condition_id)

                question = (ws_meta.get("question") if ws_meta else None) or (ws_stats.get("question") if ws_stats else None) or (cached_market.get("question") if cached_market else None) or "Unknown"
                slug = (ws_meta.get("slug") if ws_meta else None) or (ws_stats.get("slug") if ws_stats else None) or (cached_market.get("slug") if cached_market else None) or ""
                market = {
                    "conditionId": condition_id,
                    "condition_id": condition_id,
                    "id": condition_id,
                    "tokens": tokens,
                    "question": question,
                    "slug": slug,
                    "symbol": question if question != "Unknown" else (slug or condition_id[:20]),
                    "liquidity": float(cached_market.get("liquidity", 0)) if cached_market else (ws_stats.get("total_volume", 5000.0) if ws_stats else 5000.0),
                    "volume": float(cached_market.get("volume", 0)) if cached_market else (ws_stats.get("total_volume", 1000.0) if ws_stats else 1000.0),
                    "volume24hr": (ws_stats.get("total_volume", 0) if ws_stats else 0),
                    "endDate": cached_market.get("endDate") if cached_market else None,
                    # Preserve activity stats for factor evaluation
                    "_ws_stats": ws_stats,
                }
                if side == "yes":
                    token_id = ws_yes_tid
                else:
                    token_id = ws_no_tid
                # Register token -> condition mapping so get_activity works
                if token_id:
                    self._token_to_condition[token_id] = condition_id
                    if hasattr(data_source, "_token_to_condition"):
                        data_source._token_to_condition[token_id] = condition_id
                strategy_exec_logger.info("[EVAL] recovered market %s from WebSocket feed tokens=%s stats=%s", condition_id, tokens, "yes" if ws_stats else "no")

        # 2c. Last resort: broken Gamma API fallback (kept for rare cases, usually fails for hex ids)
        if not market or not token_id:
            try:
                client = self._http_client
                search_resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"conditionIds": condition_id, "limit": 1},
                )
                if search_resp.status_code == 200:
                    data = search_resp.json()
                    markets = data if isinstance(data, list) else data.get("markets", [])
                    market = markets[0] if markets else None

                if not market:
                    resp = await client.get(
                        f"https://gamma-api.polymarket.com/markets/{condition_id}",
                    )
                    if resp.status_code == 200:
                        market = resp.json()

                if market:
                    hex_cid = market.get("conditionId") or market.get("condition_id") or condition_id
                    numeric_id = market.get("id")
                    self._market_cache[hex_cid] = market
                    if numeric_id:
                        self._market_cache[str(numeric_id)] = market

                    if not market.get("tokens") and numeric_id:
                        tokens = await self._fetch_gamma_token_details(str(numeric_id))
                        if tokens:
                            market["tokens"] = tokens

                    if hasattr(data_source, "update_market_meta"):
                        yes_tid = self._get_market_yes_token_id(market)
                        if yes_tid:
                            data_source.update_market_meta(yes_tid, market)
                    if side == "yes":
                        token_id = self._get_market_yes_token_id(market)
                    else:
                        token_id = self._get_market_no_token_id(market)
                    if token_id:
                        self._token_to_condition[token_id] = hex_cid
            except Exception as e:
                strategy_exec_logger.warning("[EVAL] fetch market %s failed: %s", condition_id, repr(e))

        if not market or not token_id:
            self._record_eval("no_market")
            strategy_exec_logger.info("[EVAL] no market %s side=%s strategy=%s", condition_id, side, strategy.id)
            return None
        t2 = time.time()

        # 3. Get real-time price (price monitor caches YES token)
        yes_token_id = self._get_market_yes_token_id(market)
        no_token_id = self._get_market_no_token_id(market)
        market_data = None
        if yes_token_id:
            market_data = await data_source.get_market_data(yes_token_id)
        if not market_data and no_token_id:
            md_no = await data_source.get_market_data(no_token_id)
            if md_no:
                # Invert prices since we looked up the NO token
                market_data = MarketData(
                    market_id=no_token_id,
                    token_id=no_token_id,
                    yes_price=1 - md_no.yes_price,
                    no_price=md_no.yes_price,
                    change_24h=md_no.change_24h,
                    volume=md_no.volume,
                    hours_to_expiry=md_no.hours_to_expiry,
                    timestamp=md_no.timestamp,
                    best_bid=1 - md_no.best_ask if md_no.best_ask is not None else None,
                    best_ask=1 - md_no.best_bid if md_no.best_bid is not None else None,
                    spread=md_no.spread,
                )
        if not market_data:
            self._record_eval("no_price")
            strategy_exec_logger.info("[EVAL] no price %s yes=%s no=%s", condition_id, yes_token_id, no_token_id)
            return None

        eval_price = market_data.yes_price if side == "yes" else market_data.no_price

        # Build direction-aware MarketData for entry condition / factor evaluation
        filter_md = MarketData(
            market_id=market_data.market_id,
            token_id=token_id,
            yes_price=eval_price,
            no_price=1 - eval_price,
            change_24h=market_data.change_24h,
            volume=market_data.volume,
            hours_to_expiry=market_data.hours_to_expiry,
            timestamp=market_data.timestamp,
            best_bid=market_data.best_bid if side == "yes" else (1 - market_data.best_ask if market_data.best_ask is not None else None),
            best_ask=market_data.best_ask if side == "yes" else (1 - market_data.best_bid if market_data.best_bid is not None else None),
            spread=market_data.spread,
        )

        # Push metadata and subscribe token
        if hasattr(data_source, "update_market_meta"):
            data_source.update_market_meta(token_id, market)
        if hasattr(data_source, "subscribe"):
            try:
                await data_source.subscribe([token_id])
            except Exception:
                pass

        # 4. SignalFilter (Tier 2: price range, dead zone, expiry)
        # SignalFilter checks the market's base probability (yes_price), NOT the
        # side-specific price.  When side=no the no_price is 1-yes_price; we must
        # still filter on the underlying market level.
        filter_config = {}
        if strategy.filters and isinstance(strategy.filters, dict):
            filter_config = strategy.filters
        else:
            filter_config = {
                "min_confidence": 40,
                "min_price": 0.05,
                "max_price": 0.99,
            }
        signal_filter = SignalFilter(filter_config)

        filter_check_md = MarketData(
            market_id=market_data.market_id,
            token_id=token_id,
            yes_price=market_data.yes_price,
            no_price=market_data.no_price,
            change_24h=market_data.change_24h,
            volume=market_data.volume,
            hours_to_expiry=market_data.hours_to_expiry,
            timestamp=market_data.timestamp,
            best_bid=market_data.best_bid,
            best_ask=market_data.best_ask,
            spread=market_data.spread,
        )

        if not signal_filter.filter_market(filter_check_md):
            self._record_eval("signal_filter")
            strategy_exec_logger.info(
                "[EVAL] filter rejected %s yes_price=%.4f eval_price=%.4f side=%s range=[%.2f,%.2f] dead_zone=[%.2f,%.2f] strategy=%s",
                condition_id, market_data.yes_price, eval_price, side,
                signal_filter.min_price, signal_filter.max_price,
                signal_filter.dead_zone_min, signal_filter.dead_zone_max,
                strategy.id,
            )
            return None
        t3 = time.time()

        # 5. Keyword filter (Tier 3)
        market_name = market.get("question", market.get("symbol", ""))
        if not signal_filter.filter_by_keywords(market_name):
            self._record_eval("keyword_filter")
            strategy_exec_logger.info("[EVAL] keyword rejected %s", condition_id)
            return None

        # 6. Entry condition validation (Tier 4)
        adapter = _EntryConditionAdapter(filter_md, market)
        entry_cond_config = EntryConditionConfig(
            price_min=signal_filter.min_price,
            price_max=signal_filter.max_price,
            allow_death_zone=True,
            min_liquidity=0.0,
            min_order_book_depth=0.0,
            min_volatility=0.0,
        )
        entry_cond_validator = EntryConditionValidator(
            market_source=adapter,
            liquidity_source=adapter,
            volatility_source=adapter,
            config=entry_cond_config,
        )
        loop = asyncio.get_event_loop()
        cond_result = await loop.run_in_executor(
            self._executor,
            entry_cond_validator.validate,
            market_data.market_id or token_id,
            eval_price,
        )
        if not cond_result.can_enter:
            self._record_eval("entry_condition")
            reason = cond_result.failed_checks[0].message if cond_result.failed_checks else str(cond_result.overall_result)
            strategy_exec_logger.info("[EVAL] entry rejected %s: %s", condition_id, reason)
            return None
        t4 = time.time()

        # 7. ExpiryPolicy - unified time gate
        expiry_policy = ExpiryPolicy.from_strategy_config(filter_config)
        expiry_verdict = expiry_policy.check(market_data.hours_to_expiry)
        if expiry_verdict.action == ExpiryAction.BLOCK:
            self._record_eval("entry_condition")
            strategy_exec_logger.info("[EVAL] expiry rejected %s", condition_id)
            return None

        # 8. Activity data for factor evaluation
        activity_data = await data_source.get_activity(yes_token_id)

        # 9. Factor evaluation (Tier 6)
        buy_config = self._get_buy_strategy_config(strategy)
        buy_strategy = BuyStrategy(
            signal_generators=[],
            risk_manager=None,
            config=buy_config,
        )
        context = self._build_market_context(market, filter_md, activity_data, data_source, token_id, side=side)
        factor_output = await buy_strategy.evaluate(context)

        if factor_output.decision in (BuyDecision.PASS, BuyDecision.BLOCKED):
            self._record_eval("factor_rejected")
            strategy_exec_logger.info(
                "[EVAL] factor rejected %s scores=%s reasoning=%s",
                condition_id,
                factor_output.signal_scores,
                factor_output.reasoning,
            )
            return None

        # 9a. Sports market gate: must have live score data
        if self._is_sports_market(market) and context.sports_momentum is None:
            strategy_exec_logger.info("[EVAL] sports market %s has no live score, rejecting", condition_id)
            return None

        t5 = time.time()

        # 9. AI analysis (Tier 7) — single market, no need for top-N
        market["_triggered"] = True
        market["_side"] = side
        market["_token_id"] = token_id
        short_avg = trigger_data.get("short_window", {}).get("avg_price", eval_price)
        market["_price_change"] = (
            abs(short_avg - eval_price) / eval_price * 100
            if eval_price > 0 else 0
        )
        market["_netflow"] = trigger_data.get("short_window", {}).get("net_flow", 0)
        market["_factor_score"] = factor_output.composite_score
        market["_factor_decision"] = factor_output.decision.value
        market["_factor_confidence"] = factor_output.confidence
        market["_factor_stop_loss"] = factor_output.stop_loss
        market["_factor_take_profit"] = factor_output.take_profit
        market["_factor_reasoning"] = factor_output.reasoning
        market["_current_price"] = eval_price

        ai_result = await self._call_ai_analysis(strategy, [market], [(token_id, factor_output)])
        t6 = time.time()
        if not ai_result:
            self._record_eval("ai_none")
            strategy_exec_logger.info("[EVAL] AI none %s", condition_id)
            return None

        # 10. AI confidence filter
        confidence = ai_result.get("confidence", 0)
        min_confidence = signal_filter.min_confidence / 100
        if confidence < min_confidence:
            self._record_eval("factor_rejected")
            strategy_exec_logger.info("[EVAL] AI confidence %.2f < %.2f %s", confidence, min_confidence, condition_id)
            return None

        # 11. Update trigger time
        if trigger_checker:
            trigger_checker.update_trigger_time()

        # 12. Build SignalLog
        order_size = self._calculate_order_size(strategy, confidence)
        market_id = ai_result.get("market_id", condition_id)
        symbol = ai_result.get("symbol", market.get("symbol", ""))

        signal_log = SignalLog(
            id=uuid4(),
            user_id=strategy.user_id,
            portfolio_id=strategy.portfolio_id,
            strategy_id=strategy.id,
            signal_id=str(uuid4()),
            signal_type=ai_result.get("action", "hold"),
            confidence=Decimal(str(ai_result.get("confidence", 0))),
            side=side,
            size=Decimal(str(order_size)),
            stop_loss_price=Decimal(str(ai_result.get("stop_loss", 0))) if ai_result.get("stop_loss") else None,
            take_profit_price=Decimal(str(ai_result.get("take_profit", 0))) if ai_result.get("take_profit") else None,
            risk_reward_ratio=Decimal(str(ai_result.get("risk_reward", 0))) if ai_result.get("risk_reward") else None,
            status="approved",
            signal_reason=ai_result.get("reasoning", ""),
            ai_thinking=ai_result.get("thinking", ""),
            ai_model=ai_result.get("model", ""),
            ai_tokens_used=ai_result.get("tokens_used"),
            ai_duration_ms=ai_result.get("duration_ms"),
            input_summary=ai_result.get("input_summary"),
            decision_details=ai_result.get("decision_details"),
            market_id=market_id,
            symbol=symbol,
            signal_generated_at=datetime.utcnow(),
        )
        db.add(signal_log)
        await db.commit()
        self._record_eval("signal")

        # 13. Position limits and execution
        action = ai_result.get("action")

        if action in ["buy", "sell"]:
            from sqlalchemy import func as sa_func

            pos_count_result = await db.execute(
                select(sa_func.count()).select_from(Position).where(
                    Position.strategy_id == strategy.id,
                    Position.status == "open",
                )
            )
            current_positions = pos_count_result.scalar() or 0
            if current_positions >= strategy.max_positions:
                signal_log.status = "rejected"
                signal_log.signal_reason += " | Rejected: max positions reached"
                await db.commit()
                strategy_exec_logger.info("[EVAL] rejected: max positions %d/%d", current_positions, strategy.max_positions)
                return signal_log

            existing_result = await db.execute(
                select(Position).where(
                    Position.strategy_id == strategy.id,
                    Position.market_id == market_id,
                    Position.side == side,
                    Position.status == "open",
                )
            )
            if existing_result.scalar_one_or_none():
                signal_log.status = "rejected"
                signal_log.signal_reason += " | Rejected: duplicate open position"
                await db.commit()
                strategy_exec_logger.info("[EVAL] rejected: duplicate position %s %s", market_id, side)
                return signal_log

            await self._execute_order(db, strategy, signal_log, data_source)

        total_time = time.time() - _eval_start
        strategy_exec_logger.info(
            "[SIGNAL] %s side=%s price=%.4f conf=%.2f status=%s total=%.2fs", condition_id, side, eval_price, confidence, signal_log.status, total_time
        )
        strategy_exec_logger.info(
            "[TIMING] %s fetch=%.2fs filter=%.2fs entry=%.2fs factor=%.2fs ai=%.2fs total=%.2fs",
            condition_id, t2-t1 if 't2' in locals() else 0, t3-t2 if 't3' in locals() else 0,
            t4-t3 if 't4' in locals() else 0, t5-t4 if 't5' in locals() else 0,
            t6-t5 if 't6' in locals() else 0, total_time,
        )
        for handler in strategy_exec_logger.handlers:
            handler.flush()
        return signal_log

    async def _execute_strategy(
        self, db: AsyncSession, strategy: Strategy, data_source: DataSource
    ) -> Optional[SignalLog]:
        """Execute strategy once: filter -> factor evaluation -> AI decision -> order."""
        strategy_exec_logger.info("[EXEC] _execute_strategy started for %s", strategy.id)

        # 1. Get available markets
        markets = await self._get_available_markets(strategy, data_source)
        if not markets:
            return None

        # 2. Initialize filter and trigger
        filter_config = {}
        if strategy.filters and isinstance(strategy.filters, dict):
            filter_config = strategy.filters
        else:
            filter_config = {
                'min_confidence': 40,
                'min_price': 0.5,
                'max_price': 0.99,
            }

        signal_filter = SignalFilter(filter_config)

        # Initialize ExpiryPolicy from strategy config
        expiry_policy = ExpiryPolicy.from_strategy_config(filter_config)

        trigger_config = {}
        if strategy.trigger and isinstance(strategy.trigger, dict):
            trigger_config = strategy.trigger

        # Use persistent trigger checker per strategy (cooldown survives across iterations)
        if strategy.id not in self._trigger_checkers:
            self._trigger_checkers[strategy.id] = TriggerChecker(trigger_config)
        trigger_checker = self._trigger_checkers[strategy.id]

        # 3. Cooldown check
        if not trigger_checker.check_cooldown():
            return None

        # 4. Initialize BuyStrategy with config from strategy parameters
        buy_config = self._get_buy_strategy_config(strategy)
        self._buy_strategy = BuyStrategy(
            signal_generators=[],
            risk_manager=None,
            config=buy_config,
        )

        # Build condition_id -> CLOB token_id mapping for correct lookups
        market_token_map: Dict[str, str] = {}
        for m in markets:
            condition_id = m.get("id") or m.get("conditionId") or m.get("condition_id", "")
            token_id = self._get_market_yes_token_id(m)
            if condition_id and token_id:
                market_token_map[condition_id] = token_id
                # Maintain reverse mapping for data_source internal lookups
                self._token_to_condition[token_id] = condition_id

        # 5. Subscribe CLOB token_ids to data source for real-time updates
        token_ids = list(set(market_token_map.values()))
        if token_ids and hasattr(data_source, "subscribe"):
            try:
                await data_source.subscribe(token_ids)
                logger.info("Subscribed %d CLOB tokens to data source", len(token_ids))
            except Exception as e:
                logger.warning("Failed to subscribe tokens: %s", e)

        # 5a. Push market metadata using CLOB token_id for expiry calc
        if hasattr(data_source, "update_market_meta"):
            for condition_id, token_id in market_token_map.items():
                m = self._market_cache.get(condition_id)
                if m and token_id:
                    try:
                        data_source.update_market_meta(token_id, m)
                    except Exception:
                        pass

        # 6. Filter markets + check triggers + factor evaluation
        triggered_markets: List[dict] = []
        factor_results: List[Tuple[str, BuyDecisionOutput]] = []
        stats = {"missing_token_id": 0, "prefilter": 0, "no_price": 0, "signal_filter": 0, "keyword": 0, "entry_cond": 0, "no_trigger": 0, "factor_reject": 0, "passed": 0}

        for market in markets:
            condition_id = market.get("id") or market.get("conditionId") or market.get("condition_id", "")
            yes_token_id = market_token_map.get(condition_id)
            if not yes_token_id:
                stats["missing_token_id"] += 1
                continue

            # === Tier 1: Activity flow pre-filter (PRIMARY GATE, 60s window) ===
            activity_data = await data_source.get_activity(yes_token_id)
            if activity_data is not None:
                if abs(activity_data.netflow) < 50:
                    logger.debug(
                        "Activity pre-filter rejected %s (60s): netflow=%.2f traders=%d",
                        yes_token_id, activity_data.netflow, activity_data.unique_traders,
                    )
                    stats["prefilter"] += 1
                    continue

            # Determine side from netflow direction
            netflow = activity_data.netflow if activity_data else 0
            side = "yes" if netflow >= 0 else "no"

            # Get token for chosen side
            if side == "yes":
                token_id = yes_token_id
            else:
                token_id = await self._get_token_id(condition_id, "no")
                if not token_id:
                    stats["missing_token_id"] += 1
                    continue

            # Get real-time price data (price monitor caches YES token)
            market_data = await data_source.get_market_data(yes_token_id)
            if not market_data:
                stats["no_price"] += 1
                continue

            eval_price = market_data.yes_price if side == "yes" else market_data.no_price

            # Build direction-aware MarketData for filtering / validation
            filter_md = MarketData(
                market_id=market_data.market_id,
                token_id=token_id,
                yes_price=eval_price,
                no_price=1 - eval_price,
                change_24h=market_data.change_24h,
                volume=market_data.volume,
                hours_to_expiry=market_data.hours_to_expiry,
                timestamp=market_data.timestamp,
                best_bid=market_data.best_bid if side == "yes" else (1 - market_data.best_ask if market_data.best_ask is not None else None),
                best_ask=market_data.best_ask if side == "yes" else (1 - market_data.best_bid if market_data.best_bid is not None else None),
                spread=market_data.spread,
            )

            # Apply SignalFilter (price range, dead zone, expiry)
            if not signal_filter.filter_market(filter_md):
                strategy_exec_logger.info("[EXEC] signal filter rejected %s side=%s price=%.4f", condition_id, side, eval_price)
                stats["signal_filter"] += 1
                continue

            # Keyword filter
            market_name = market.get("question", market.get("symbol", ""))
            if not signal_filter.filter_by_keywords(market_name):
                stats["keyword"] += 1
                continue

            # === Layer 2: Entry Condition Validation ===
            adapter = _EntryConditionAdapter(filter_md, market)
            entry_cond_config = EntryConditionConfig(
                price_min=0.05,
                price_max=0.95,
                allow_death_zone=True,
                min_liquidity=1000.0,
                min_order_book_depth=500.0,
                min_volatility=0.0,
            )
            entry_cond_validator = EntryConditionValidator(
                market_source=adapter,
                liquidity_source=adapter,
                volatility_source=adapter,
                config=entry_cond_config,
            )
            loop = asyncio.get_event_loop()
            cond_result = await loop.run_in_executor(
                self._executor,
                entry_cond_validator.validate,
                market_data.market_id or token_id,
                eval_price,
            )
            if not cond_result.can_enter:
                failed = cond_result.failed_checks
                reason = failed[0].message if failed else str(cond_result.overall_result)
                strategy_exec_logger.info("[EXEC] entry condition rejected %s side=%s: %s", condition_id, side, reason)
                stats["entry_cond"] += 1
                continue

            # ExpiryPolicy - unified time gate
            expiry_verdict = expiry_policy.check(market_data.hours_to_expiry)
            if expiry_verdict.action == ExpiryAction.BLOCK:
                logger.info("ExpiryPolicy rejected %s: %s", market_data.market_id, expiry_verdict.reason)
                stats["entry_cond"] += 1
                continue

            # Trigger check (price change + netflow)
            raw_old_price = market.get("price")
            new_price = eval_price

            if raw_old_price is not None:
                price_triggered = trigger_checker.check_price_trigger(float(raw_old_price), new_price)
            else:
                price_triggered = True
                logger.debug("Price trigger skipped for %s (first scan)", token_id)

            activity_triggered = trigger_checker.check_activity_trigger(netflow, new_price)
            should_trigger = price_triggered and (activity_triggered if activity_data is not None else True)

            # Sports event override
            sports_triggered = False
            if hasattr(data_source, "get_sports_signal"):
                sports_signal = data_source.get_sports_signal(token_id)
                if sports_signal and sports_signal.get("strength") == "strong":
                    sports_triggered = True
                    logger.info("Sports strong signal override for %s: %s", token_id, sports_signal.get("reason"))

            if sports_triggered:
                should_trigger = True

            if not should_trigger:
                stats["no_trigger"] += 1
                logger.debug(
                    "Trigger check failed %s: price_triggered=%s activity_triggered=%s has_activity=%s",
                    token_id, price_triggered, activity_triggered, activity_data is not None,
                )
                continue

            stats["passed"] += 1

            # === Factor Evaluation ===
            context = self._build_market_context(market, filter_md, activity_data, data_source, token_id, side=side)
            loop = asyncio.get_event_loop()
            factor_output = await loop.run_in_executor(
                self._executor,
                self._buy_strategy.evaluate,
                context,
            )

            # Filter by factor score: PASS or BLOCKED skip
            if factor_output.decision in (BuyDecision.PASS, BuyDecision.BLOCKED):
                stats["factor_reject"] += 1
                continue

            # Store factor result
            factor_results.append((token_id, factor_output))

            # Enrich market with trigger and factor info for AI
            market["_triggered"] = True
            market["_side"] = side
            market["_token_id"] = token_id
            raw_old_price = market.get("price")
            old_price = float(raw_old_price) if raw_old_price is not None else new_price
            market["_price_change"] = abs(new_price - old_price) / old_price * 100 if old_price > 0 else 0
            market["_netflow"] = netflow
            market["_factor_score"] = factor_output.composite_score
            market["_factor_decision"] = factor_output.decision.value
            market["_factor_confidence"] = factor_output.confidence
            market["_factor_stop_loss"] = factor_output.stop_loss
            market["_factor_take_profit"] = factor_output.take_profit
            market["_factor_reasoning"] = factor_output.reasoning
            market["_current_price"] = new_price

            triggered_markets.append(market)

        strategy_exec_logger.info(
            "[FILTER] total=%d missing_token_id=%d prefilter=%d no_price=%d signal_filter=%d keyword=%d entry_cond=%d no_trigger=%d factor_reject=%d passed=%d",
            len(markets), stats["missing_token_id"], stats["prefilter"], stats["no_price"], stats["signal_filter"], stats["keyword"], stats["entry_cond"], stats["no_trigger"], stats["factor_reject"], stats["passed"],
        )
        for handler in strategy_exec_logger.handlers:
            handler.flush()

        if not triggered_markets:
            strategy_exec_logger.info("[EXEC] no triggered markets after filter, returning None")
            for handler in strategy_exec_logger.handlers:
                handler.flush()
            return None

        # Sort by factor score descending, take top candidates
        triggered_markets.sort(key=lambda m: m.get("_factor_score", 0), reverse=True)
        top_markets = triggered_markets[:5]  # Send top 5 to AI

        # 6. Call AI analysis with factor scores as context
        ai_result = await self._call_ai_analysis(strategy, top_markets, factor_results)
        if not ai_result:
            strategy_exec_logger.info("[EXEC] AI analysis returned None")
            for handler in strategy_exec_logger.handlers:
                handler.flush()
            return None

        # 7. AI confidence filter
        confidence = ai_result.get("confidence", 0)
        min_confidence = signal_filter.min_confidence / 100
        if confidence < min_confidence:
            strategy_exec_logger.info("[EXEC] AI confidence %.2f < min %.2f, skipping", confidence, min_confidence)
            for handler in strategy_exec_logger.handlers:
                handler.flush()
            return None

        # 8. Use factor-calculated stop-loss / take-profit as fallback if AI didn't provide
        selected_market = None
        market_id = ai_result.get("market_id", "")
        for m in top_markets:
            if m.get("id") == market_id or m.get("symbol") == ai_result.get("symbol", ""):
                selected_market = m
                break
        if not selected_market and top_markets:
            selected_market = top_markets[0]

        if selected_market:
            if not ai_result.get("stop_loss") and selected_market.get("_factor_stop_loss"):
                ai_result["stop_loss"] = selected_market["_factor_stop_loss"]
            if not ai_result.get("take_profit") and selected_market.get("_factor_take_profit"):
                ai_result["take_profit"] = selected_market["_factor_take_profit"]
            if not ai_result.get("market_id"):
                ai_result["market_id"] = selected_market.get("id", "")
            if not ai_result.get("symbol"):
                ai_result["symbol"] = selected_market.get("symbol", "")

        # 9. Update trigger time
        trigger_checker.update_trigger_time()

        # 10. Calculate order size
        order_size = self._calculate_order_size(strategy, confidence)

        # 11. Create SignalLog
        market_id = ai_result.get("market_id", "")
        symbol = ai_result.get("symbol", "")
        side = selected_market.get("_side", "yes") if selected_market else "yes"

        signal_log = SignalLog(
            id=uuid4(),
            user_id=strategy.user_id,
            portfolio_id=strategy.portfolio_id,
            strategy_id=strategy.id,
            signal_id=str(uuid4()),
            signal_type=ai_result.get("action", "hold"),
            confidence=Decimal(str(ai_result.get("confidence", 0))),
            side=side,
            size=Decimal(str(order_size)),
            stop_loss_price=Decimal(str(ai_result.get("stop_loss", 0))) if ai_result.get("stop_loss") else None,
            take_profit_price=Decimal(str(ai_result.get("take_profit", 0))) if ai_result.get("take_profit") else None,
            risk_reward_ratio=Decimal(str(ai_result.get("risk_reward", 0))) if ai_result.get("risk_reward") else None,
            status="approved",
            signal_reason=ai_result.get("reasoning", ""),
            ai_thinking=ai_result.get("thinking", ""),
            ai_model=ai_result.get("model", ""),
            ai_tokens_used=ai_result.get("tokens_used"),
            ai_duration_ms=ai_result.get("duration_ms"),
            input_summary=ai_result.get("input_summary"),
            decision_details=ai_result.get("decision_details"),
            market_id=market_id,
            symbol=symbol,
            signal_generated_at=datetime.utcnow(),
        )

        db.add(signal_log)
        await db.commit()

        # 12. Position limits check before execution
        action = ai_result.get("action")

        if action in ["buy", "sell"]:
            from sqlalchemy import func as sa_func

            # Check max positions limit
            pos_count_result = await db.execute(
                select(sa_func.count()).select_from(Position).where(
                    Position.strategy_id == strategy.id,
                    Position.status == "open"
                )
            )
            current_positions = pos_count_result.scalar() or 0
            if current_positions >= strategy.max_positions:
                signal_log.status = "rejected"
                signal_log.signal_reason += " | Rejected: max positions reached"
                await db.commit()
                logger.info("Signal rejected: max positions %d/%d", current_positions, strategy.max_positions)
                return signal_log

            # Check duplicate position (same market + side)
            existing_result = await db.execute(
                select(Position).where(
                    Position.strategy_id == strategy.id,
                    Position.market_id == market_id,
                    Position.side == side,
                    Position.status == "open"
                )
            )
            if existing_result.scalar_one_or_none():
                signal_log.status = "rejected"
                signal_log.signal_reason += " | Rejected: duplicate open position"
                await db.commit()
                logger.info("Signal rejected: duplicate position %s %s", market_id, side)
                return signal_log

            # Execute order
            await self._execute_order(db, strategy, signal_log, data_source)

        strategy_exec_logger.info("[EXEC] returning signal_log type=%s status=%s", signal_log.signal_type, signal_log.status)
        for handler in strategy_exec_logger.handlers:
            handler.flush()
        return signal_log

    async def _sync_onchain_positions(
        self, db: AsyncSession, strategy: Strategy
    ) -> List[Dict[str, Any]]:
        """Sync on-chain positions from proxy wallet via CLOB API.

        Returns list of on-chain position dicts with token_id, market_id, side, size, price.
        Also updates DB positions to match on-chain state.
        """
        if not self.clob_client:
            return []

        try:
            # Resolve wallet address for data-api query
            wallet_result = await db.execute(
                select(Wallet)
                .where(Wallet.user_id == strategy.user_id, Wallet.is_default == True)
                .limit(1)
            )
            wallet = wallet_result.scalar_one_or_none()
            user_address = (wallet.proxy_wallet_address if wallet else None) or (wallet.address if wallet else None)
            if not user_address:
                logger.warning("No default wallet address for positions fetch")
                return []

            async with httpx.AsyncClient(timeout=15.0, proxy=self._proxy_url) as client:
                resp = await client.get(
                    f"https://data-api.polymarket.com/positions",
                    params={"user": user_address},
                )
                resp.raise_for_status()
                raw_positions = resp.json()

            if not raw_positions:
                return []

            # Normalize to list of dicts
            onchain_list: List[Dict[str, Any]] = []
            if isinstance(raw_positions, dict):
                raw_positions = raw_positions.get("positions", raw_positions.get("data", []))
            if not isinstance(raw_positions, list):
                return []

            for p in raw_positions:
                if not isinstance(p, dict):
                    continue
                size = float(p.get("quantity") or p.get("size") or p.get("amount", 0))
                if size <= 0:
                    continue  # Skip zero/closed positions

                # Skip positions with zero current value (settled/dust)
                current_value = float(p.get("currentValue") or p.get("current_value") or p.get("value", size))
                if current_value <= 0:
                    continue

                token_id = p.get("token_id") or p.get("asset_id") or ""
                market_id = p.get("market_id") or p.get("condition_id") or ""
                side = (p.get("outcome") or p.get("position") or "yes").lower()

                onchain_list.append({
                    "token_id": token_id,
                    "market_id": market_id,
                    "side": side if side in ("yes", "no") else "yes",
                    "size": Decimal(str(size)),
                    "avg_price": float(p.get("avg_buy_price") or p.get("avg_price") or p.get("entry_price", 0.5)),
                })

            # Sync with DB: get all open positions for this strategy
            result = await db.execute(
                select(Position).where(
                    Position.strategy_id == strategy.id,
                    Position.status == "open"
                )
            )
            db_positions = result.scalars().all()
            db_by_market_side = {(p.market_id, p.side): p for p in db_positions}
            onchain_keys = set()

            # 1. Update existing / create new from on-chain
            data_source = self._data_source_manager._sources.get(strategy.portfolio_id)
            for ocp in onchain_list:
                key = (ocp["market_id"], ocp["side"])
                onchain_keys.add(key)

                if key in db_by_market_side:
                    # Update existing position size/price if changed
                    dbp = db_by_market_side[key]
                    if dbp.size != ocp["size"]:
                        dbp.size = ocp["size"]
                        dbp.notes = (dbp.notes or "") + f" | On-chain sync: size updated to {ocp['size']}"
                else:
                    # On-chain position not in DB (possibly manual trade) — create record
                    new_pos = Position(
                        id=uuid4(),
                        portfolio_id=strategy.portfolio_id,
                        strategy_id=strategy.id,
                        market_id=ocp["market_id"],
                        symbol=ocp["market_id"],
                        side=ocp["side"],
                        status="open",
                        size=ocp["size"],
                        entry_price=Decimal(str(ocp["avg_price"])),
                        current_price=Decimal(str(ocp["avg_price"])),
                        average_entry_price=Decimal(str(ocp["avg_price"])),
                        opened_at=datetime.utcnow(),
                        last_updated_at=datetime.utcnow(),
                        source="on_chain_sync",
                    )
                    db.add(new_pos)
                    await db.flush()  # Flush to get new_pos.id assigned
                    logger.info("On-chain position synced: %s %s size=%s", ocp['market_id'], ocp['side'], ocp['size'])

                    # Register with flow exit and sports monitor
                    self._flow_exit.register_position(
                        position_id=str(new_pos.id),
                        entry_price=ocp["avg_price"],
                        size=float(ocp["size"]),
                        side="long" if ocp["side"] == "yes" else "short"
                    )
                    if data_source and hasattr(data_source, "register_sports_position"):
                        data_source.register_sports_position(
                            position_id=str(new_pos.id),
                            market_id=ocp["market_id"],
                            entry_price=ocp["avg_price"],
                            stop_loss_pct=0.10,
                            side=ocp["side"],
                        )

            # 2. Close DB positions that no longer exist on-chain
            for key, dbp in db_by_market_side.items():
                if key not in onchain_keys:
                    dbp.close_position(dbp.current_price or dbp.entry_price, datetime.utcnow())
                    dbp.notes = (dbp.notes or "") + " | Closed: no longer on-chain"
                    logger.info("Position closed (not on-chain): %s %s %s", dbp.id, dbp.market_id, dbp.side)
                    # Unregister from sports monitor
                    if data_source and hasattr(data_source, "unregister_sports_position"):
                        data_source.unregister_sports_position(str(dbp.id))

            await db.commit()
            return onchain_list

        except Exception as e:
            logger.exception("On-chain position sync failed: %s", e)
            return []

    async def _monitor_positions(
        self,
        db: AsyncSession,
        strategy: Strategy,
        data_source: DataSource,
        onchain_positions: List[Dict[str, Any]],
    ) -> None:
        """Monitor open positions: fixed rules first, then flow-assisted.

        Uses on-chain synced positions for monitoring.
        """
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy.id,
                Position.status == "open"
            )
        )
        positions = result.scalars().all()
        if not positions:
            return

        # Subscribe on-chain position token_ids to data source for real-time exit monitoring
        onchain_token_ids = [p["token_id"] for p in onchain_positions if p.get("token_id")]
        if onchain_token_ids and hasattr(data_source, "subscribe"):
            try:
                await data_source.subscribe(onchain_token_ids)
                logger.info("Subscribed %d on-chain position tokens to WebSocket", len(onchain_token_ids))
            except Exception as e:
                logger.warning("Failed to subscribe on-chain position tokens: %s", e)

        for pos in positions:
            try:
                # Get current price (WebSocket real-time or HTTP fallback)
                market_data = await data_source.get_market_data(pos.market_id)
                if not market_data:
                    continue

                current_price = market_data.yes_price if pos.side == "yes" else market_data.no_price
                pos.current_price = Decimal(str(current_price))
                pos.calculate_unrealized_pnl(pos.current_price)

                # === Fixed exit rules (no AI needed) ===
                # 1. Extreme take-profit: price >= 0.999
                if current_price >= 0.999:
                    await self._close_position(
                        db, strategy, pos, current_price,
                        "fixed_take_profit: price reached 0.999",
                        exit_type="fixed"
                    )
                    continue

                # 2. Fixed stop-loss (respect strategy flag)
                if strategy.enable_stop_loss and pos.stop_loss_price and current_price <= float(pos.stop_loss_price):
                    await self._close_position(
                        db, strategy, pos, current_price,
                        f"fixed_stop_loss: price {current_price:.3f} <= stop {float(pos.stop_loss_price):.3f}",
                        exit_type="fixed"
                    )
                    continue

                # 3. Fixed take-profit (respect strategy flag)
                if strategy.enable_take_profit and pos.take_profit_price and current_price >= float(pos.take_profit_price):
                    await self._close_position(
                        db, strategy, pos, current_price,
                        f"fixed_take_profit: price {current_price:.3f} >= target {float(pos.take_profit_price):.3f}",
                        exit_type="fixed"
                    )
                    continue

                # === Sports score + Activity flow combined exit ===
                if hasattr(data_source, "get_combined_sports_exit_signal"):
                    sports_signal = data_source.get_combined_sports_exit_signal(
                        str(pos.id), pos.market_id
                    )
                    if sports_signal:
                        action = sports_signal.get("action", "")
                        if action in ("exit_immediately", "exit"):
                            await self._close_position(
                                db, strategy, pos, current_price,
                                sports_signal["reason"],
                                exit_type="sports_flow_combined"
                            )
                            continue
                        elif action == "hold":
                            # Update notes but don't exit, skip P3 flow-assisted exit
                            # P2 decision combines sports + activity flow, higher quality than P3
                            pos.notes = (pos.notes or "") + f" | {sports_signal['reason']}"
                            continue

                # === Flow-assisted exit (for non-fixed scenarios) ===
                # Feed activity data to flow calculator
                activity_data = await data_source.get_activity(pos.market_id)
                if activity_data:
                    self._flow_exit.calculator.add_minute_flow(
                        datetime.utcnow(), activity_data.netflow
                    )

                # Register position with flow exit system
                self._flow_exit.register_position(
                    position_id=str(pos.id),
                    entry_price=float(pos.entry_price),
                    size=float(pos.size),
                    side="long" if pos.side == "yes" else "short"
                )

                # Check exit conditions with flow-assisted decision
                decision = self._flow_exit.check_exit_conditions(
                    position_id=str(pos.id),
                    current_price=current_price,
                    price_signal=None
                )

                if decision.action in (
                    DecisionAction.EXIT_IMMEDIATELY,
                    DecisionAction.ACCELERATE_EXIT,
                ):
                    reasoning = "; ".join(decision.reasoning[:3])
                    await self._close_position(
                        db, strategy, pos, current_price,
                        f"flow_assisted: {decision.action.value}, {reasoning}",
                        exit_type="flow_assisted"
                    )

            except Exception as e:
                logger.error("Position monitoring error for %s: %s", pos.id, e)
                continue

        await db.commit()

    async def _close_position(
        self,
        db: AsyncSession,
        strategy: Strategy,
        position: Position,
        current_price: float,
        reason: str,
        exit_type: str = "fixed"
    ) -> None:
        """Close an open position by placing a reverse market order and log sell signal."""
        if not self.clob_client:
            logger.error("ClobClient not initialized, cannot close position")
            return

        try:
            # Get token_id for the position's side
            token_id = await self._get_token_id(position.market_id, position.side)
            if not token_id:
                logger.warning("Token not found for position %s", position.id)
                return

            from py_clob_client_v2 import MarketOrderArgs, PartialCreateOrderOptions, OrderType
            from py_clob_client_v2.order_utils import Side

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=float(position.size),
                side=Side.SELL,
            )
            options = PartialCreateOrderOptions(tick_size="0.01")

            result = await asyncio.to_thread(
                self.clob_client.create_and_post_market_order,
                order_args,
                options,
                OrderType.IOC,
            )

            # Update position
            exit_price = Decimal(str(current_price))
            position.close_position(exit_price, datetime.utcnow())
            position.notes = f"Closed by strategy: {reason}"

            # Create closing order record
            close_order = Order(
                id=uuid4(),
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                position_id=position.id,
                market_id=position.market_id,
                symbol=position.symbol,
                side=position.side,
                order_type="market",
                time_in_force="IOC",
                size=position.size,
                filled_size=Decimal(str(result.get("size", position.size))),
                status="filled",
                avg_fill_price=exit_price,
                total_cost=exit_price * position.size,
                source="auto_close",
            )
            db.add(close_order)

            # Create SELL signal log for frontend display
            ai_thinking = (
                f"Exit type: {exit_type}.\n"
                + (reason if exit_type != "fixed" else "Fixed rule triggered. No AI analysis needed.")
            )
            sell_signal = SignalLog(
                id=uuid4(),
                user_id=strategy.user_id,
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                signal_id=str(uuid4()),
                signal_type="sell",
                confidence=Decimal("1.0") if exit_type == "fixed" else Decimal("0.75"),
                side=position.side,
                size=position.size,
                status="executed",
                signal_reason=reason,
                ai_thinking=ai_thinking,
                ai_model="system" if exit_type == "fixed" else "flow_assisted",
                market_id=position.market_id,
                symbol=position.symbol,
            )
            db.add(sell_signal)

            await db.commit()

            # Unregister from sports monitor
            data_source = self._data_source_manager._sources.get(strategy.portfolio_id)
            if data_source and hasattr(data_source, "unregister_sports_position"):
                data_source.unregister_sports_position(str(position.id))

            logger.info("Position closed: %s, reason=%s, pnl=%s", position.id, reason, position.realized_pnl)

        except Exception as e:
            logger.exception("Close position failed for %s: %s", position.id, e)

    async def _fetch_gamma_token_details(self, numeric_id: str) -> Optional[list[dict]]:
        """Fetch token details from Gamma single-market API by numeric id.

        Gamma /markets/{id} returns 'clobTokenIds' as a JSON string array,
        which is no longer included in the /markets list response.
        """
        try:
            resp = await self._http_client.get(
                f"https://gamma-api.polymarket.com/markets/{numeric_id}",
            )
            if resp.status_code != 200:
                strategy_exec_logger.debug("[GAMMA] token details %s returned %s", numeric_id, resp.status_code)
                return None
            data = resp.json()

            clob_ids_raw = data.get("clobTokenIds")
            outcomes_raw = data.get("outcomes")
            if not clob_ids_raw:
                strategy_exec_logger.debug("[GAMMA] no clobTokenIds for %s", numeric_id)
                return None

            # Handle both JSON-string and raw-list formats
            import json
            if isinstance(clob_ids_raw, str):
                clob_ids = json.loads(clob_ids_raw)
            elif isinstance(clob_ids_raw, list):
                clob_ids = clob_ids_raw
            else:
                clob_ids = []

            if isinstance(outcomes_raw, str):
                outcomes = json.loads(outcomes_raw)
            elif isinstance(outcomes_raw, list):
                outcomes = outcomes_raw
            else:
                outcomes = []

            tokens = []
            for i, tid in enumerate(clob_ids):
                outcome = outcomes[i] if i < len(outcomes) else ""
                tokens.append({"token_id": str(tid), "outcome": outcome})
            strategy_exec_logger.debug("[GAMMA] fetched %d tokens for market %s", len(tokens), numeric_id)
            return tokens
        except Exception as e:
            strategy_exec_logger.warning("[GAMMA] failed to fetch token details for %s: %s", numeric_id, e)
            return None

    async def _get_available_markets(
        self, strategy: Strategy, data_source: Optional[Any] = None
    ) -> list[dict]:
        """Fetch available markets from WebSocket activity (primary) or Gamma API (fallback).

        Primary source: ActivityAnalyzer hot markets (WebSocket-driven, real-time).
        Fallback: Gamma API list when activity data is insufficient.
        """
        # 1. Try cache first
        cached = self._get_cached_markets()
        if cached:
            return cached

        # 2. Primary: get hot markets from ActivityAnalyzer via data_source
        if data_source is not None and hasattr(data_source, "get_hot_markets"):
            try:
                hot_markets = data_source.get_hot_markets(limit=50, min_score=0.0)
                if hot_markets:
                    # Filter out markets without token_id (can't get price without it)
                    valid = [m for m in hot_markets if m.get("token_id")]
                    strategy_exec_logger.info(
                        "[ACTIVITY] hot markets: %d total, %d with token_id",
                        len(hot_markets), len(valid),
                    )
                    if valid:
                        self._cache_markets(valid, incremental=True)
                        # Return enriched versions from cache if available
                        enriched = []
                        for m in valid:
                            cid = m.get("conditionId") or m.get("condition_id") or m.get("id", "")
                            if cid and cid in self._market_cache:
                                enriched.append(self._market_cache[cid])
                            else:
                                enriched.append(m)
                        return enriched
            except Exception as e:
                logger.warning("Activity hot markets failed: %s", e)

        # 3. Fallback: fetch from Gamma API (paginated)
        try:
            all_markets: List[dict] = []
            offset = 0
            page_limit = 1000
            max_pages = 10
            async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                for page in range(max_pages):
                    resp = await client.get(
                        "https://gamma-api.polymarket.com/markets",
                        params={
                            "active": "true",
                            "closed": "false",
                            "limit": page_limit,
                            "offset": offset,
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    page_markets = data if isinstance(data, list) else data.get("markets", [])
                    if not page_markets:
                        break
                    all_markets.extend(page_markets)
                    if len(page_markets) < page_limit:
                        break
                    offset += page_limit

            markets = all_markets
            strategy_exec_logger.info("[GAMMA] raw response: %d markets", len(markets))

            def _parse_volume(m: dict) -> float:
                v = m.get("volume", 0)
                if v is None:
                    return 0.0
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return 0.0

            filtered = [m for m in markets if m.get("active") and _parse_volume(m) > 1000]
            strategy_exec_logger.info("[GAMMA] after filter (active + volume>1000): %d markets", len(filtered))
            for handler in strategy_exec_logger.handlers:
                handler.flush()

            # Supplement token data from Gamma single-market API
            import asyncio
            tasks = []
            market_idx = []
            for idx, m in enumerate(filtered):
                if m.get("tokens"):
                    continue
                numeric_id = m.get("id")
                if numeric_id:
                    tasks.append(self._fetch_gamma_token_details(str(numeric_id)))
                    market_idx.append(idx)

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                supplemented = 0
                for idx, tokens in zip(market_idx, results):
                    if isinstance(tokens, list) and tokens:
                        filtered[idx]["tokens"] = tokens
                        supplemented += 1
                if supplemented:
                    strategy_exec_logger.info("[GAMMA] supplemented tokens for %d markets", supplemented)

            self._cache_markets(filtered, incremental=True)
            logger.info("Fetched %d markets from Gamma API (fallback)", len(filtered))
            return filtered

        except Exception as e:
            logger.error("Failed to fetch markets from Gamma API: %s", e)
            return []

    def _get_buy_strategy_config(self, strategy: Strategy) -> BuyStrategyConfig:
        """Build BuyStrategyConfig from strategy parameters."""
        params = strategy.parameters or {}
        return BuyStrategyConfig(
            odds_bias_weight=params.get("odds_bias_weight", 0.25),
            time_decay_weight=params.get("time_decay_weight", 0.15),
            orderbook_weight=params.get("orderbook_weight", 0.20),
            capital_flow_weight=params.get("capital_flow_weight", 0.20),
            information_edge_weight=params.get("information_edge_weight", 0.20),
            strong_buy_threshold=params.get("strong_buy_threshold", 0.80),
            buy_threshold=params.get("buy_threshold", 0.30),
            hold_threshold=params.get("hold_threshold", 0.20),
            max_single_position_pct=float(strategy.max_position_size) / 100
            if strategy.max_position_size and strategy.max_position_size > 0
            else 0.10,
            max_total_positions=strategy.max_positions or 20,
            min_liquidity=float(strategy.min_liquidity) if strategy.min_liquidity else 0.0,
            enable_death_zone_check=False,
            min_odds_edge=params.get("min_odds_edge", 0.01),
            min_imbalance_ratio=params.get("min_imbalance_ratio", -1.0),
            min_smart_money_threshold=params.get("min_smart_money_threshold", -1.0),
        )

    def _is_sports_market(self, market: dict) -> bool:
        """Check if a market is a sports market based on metadata."""
        category = market.get("category", "")
        if isinstance(category, str) and "sport" in category.lower():
            return True
        tags = market.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and "sport" in tag.lower():
                    return True
        question = market.get("question", "")
        if isinstance(question, str):
            sports_keywords = [" vs ", " versus ", "win the ", "championship", "super bowl", "world cup", "nba", "nfl", "mlb", "fifa"]
            q_lower = question.lower()
            for kw in sports_keywords:
                if kw in q_lower:
                    return True
        return False

    def _build_market_context(
        self,
        market: dict,
        market_data: MarketData,
        activity_data: Optional[ActivityData],
        data_source: DataSource,
        token_id: str,
        side: str = "yes",
    ) -> BuyMarketContext:
        """Build BuyStrategy MarketContext from available data."""
        current_price = market_data.yes_price

        # 1. Odds Bias: distance from 0.5 implies conviction
        distance_from_mid = abs(current_price - 0.5)
        odds_bias = OddsBiasMetrics(
            implied_probability=current_price,
            estimated_true_probability=min(1.0, max(0.0, current_price + (current_price - 0.5) * 0.1)),
            edge=distance_from_mid,
            confidence=min(1.0, 0.5 + distance_from_mid),
        )

        # 2. Time Decay
        hours_to_expiry = market_data.hours_to_expiry or 0
        if hours_to_expiry <= 0:
            end_date_str = market.get("endDate")
            if end_date_str:
                try:
                    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    hours_to_expiry = max(0, (end_dt - datetime.utcnow()).total_seconds() / 3600)
                except Exception:
                    hours_to_expiry = 24

        days_to_expiry = max(0.01, hours_to_expiry / 24)
        urgency = 1.0 if days_to_expiry < 0.5 else (0.8 if days_to_expiry < 2 else (0.5 if days_to_expiry < 7 else 0.3))

        time_decay = TimeDecayMetrics(
            time_to_expiry=timedelta(hours=hours_to_expiry),
            theta_decay_rate=0.05 / days_to_expiry,
            optimal_holding_period=timedelta(hours=min(hours_to_expiry * 0.5, 48)),
            urgency_score=urgency,
        )

        # 3. Orderbook Pressure (from WebSocket price data)
        orderbook_pressure = None
        if market_data.best_bid is not None and market_data.best_ask is not None:
            spread = market_data.spread or (market_data.best_ask - market_data.best_bid)
            mid_price = (market_data.best_bid + market_data.best_ask) / 2
            # Imbalance: simple proxy based on price position within bid-ask spread
            if mid_price > 0:
                position_in_spread = (current_price - market_data.best_bid) / spread if spread > 0 else 0.5
                imbalance = (position_in_spread - 0.5) * 2  # -1 to 1
            else:
                imbalance = 0.0
            orderbook_pressure = OrderbookPressureMetrics(
                bid_ask_spread=spread,
                bid_depth=market_data.bid_depth or 0,
                ask_depth=market_data.ask_depth or 0,
                imbalance_ratio=imbalance,
                price_impact=spread * 0.5,
            )

        # 4. Capital Flow from activity data
        capital_flow = None
        if activity_data:
            total_volume = activity_data.buy_volume + activity_data.sell_volume
            if total_volume > 0:
                net_ratio = activity_data.netflow / total_volume
                # Flip sign for NO side so net inflow into NO is favorable
                if side == "no":
                    net_ratio = -net_ratio
                capital_flow = CapitalFlowMetrics(
                    smart_money_flow=min(1.0, max(-1.0, net_ratio * 2)),
                    retail_flow=0.0,  # placeholder: not currently used by BuyStrategy
                    institutional_flow=0.0,  # placeholder: not currently used by BuyStrategy
                    flow_strength=min(1.0, abs(net_ratio) * 2 + 0.1),
                    trend_alignment=min(1.0, max(-1.0, net_ratio)),
                )

        # 5. Sports Momentum (from live score cache)
        sports_momentum = None
        if hasattr(data_source, "get_sports_signal"):
            sports_signal = data_source.get_sports_signal(token_id)
            if sports_signal:
                score_state = sports_signal.get("score_state", {})
                sports_momentum = SportsMomentumMetrics(
                    score_diff=abs(
                        score_state.get("home_score", 0) - score_state.get("away_score", 0)
                    ),
                    time_remaining=score_state.get("time_remaining", 90),
                    game_status=score_state.get("game_status", "unknown"),
                    momentum_score=0.8 if sports_signal.get("strength") == "strong" else (
                        0.5 if sports_signal.get("strength") == "moderate" else 0.2
                    ),
                    event_strength=sports_signal.get("strength", "weak"),
                )

        # Ensure numeric types (JSON fields may be strings)
        try:
            liquidity_val = float(market.get("liquidity", 0) or 0)
        except (ValueError, TypeError):
            liquidity_val = 0.0
        try:
            volume_val = float(market_data.volume or market.get("volume", 0) or 0)
        except (ValueError, TypeError):
            volume_val = 0.0

        return BuyMarketContext(
            market_id=market.get("id", ""),
            outcome_id=token_id or market.get("token_id", ""),
            current_price=current_price,
            current_odds=current_price,
            timestamp=datetime.utcnow(),
            volume_24h=volume_val,
            liquidity=liquidity_val,
            odds_bias=odds_bias,
            time_decay=time_decay,
            orderbook_pressure=orderbook_pressure,
            capital_flow=capital_flow,
            information_edge=None,
            sports_momentum=sports_momentum,
        )

    async def _call_ai_analysis(
        self, strategy: Strategy, markets: list[dict], factor_results: List[Tuple[str, BuyDecisionOutput]]
    ) -> Optional[dict]:
        """Call AI to analyze markets with factor scores as structured context."""
        import json

        # Get Provider config (cached per strategy)
        provider = None
        if strategy.provider_id:
            cached = self._provider_cache.get(strategy.id)
            if cached is not None:
                provider = cached
            else:
                try:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Provider).where(Provider.id == strategy.provider_id)
                        )
                        provider = result.scalar_one_or_none()
                        self._provider_cache[strategy.id] = provider
                except Exception as e:
                    logger.warning("Provider query failed for strategy %s: %s", strategy.id, e)
                    self._provider_cache[strategy.id] = None

        if not provider or not provider.api_key:
            logger.warning("No provider or API key found for strategy %s", strategy.id)
            return None

        # Build prompts
        system_prompt = strategy.system_prompt or self._get_default_system_prompt()
        user_prompt = self._build_user_prompt(strategy, markets, factor_results)

        # API request setup
        api_base = provider.api_base or self._get_default_api_base(provider.provider_type)
        model = provider.model or "gpt-4o"
        temperature = provider.temperature or 0.7
        max_tokens = provider.max_tokens or 2000

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}",
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "trading_signal",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                            "side": {"type": "string", "enum": ["yes", "no"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reasoning": {"type": "string"},
                            "thinking": {"type": "string"},
                            "stop_loss": {"type": "number"},
                            "take_profit": {"type": "number"},
                            "risk_reward": {"type": "number"},
                            "market_id": {"type": "string"},
                            "symbol": {"type": "string"},
                        },
                        "required": ["action", "side", "confidence", "reasoning"],
                    },
                },
            },
        }

        start_time = datetime.utcnow()

        async with self._ai_semaphore:
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=60.0, proxy=self._proxy_url) as client:
                        response = await client.post(
                            f"{api_base}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        response.raise_for_status()
                        result = response.json()

                    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                    content = result["choices"][0]["message"]["content"]
                    ai_result = json.loads(content)

                    ai_result["model"] = model
                    ai_result["duration_ms"] = duration_ms
                    ai_result["tokens_used"] = result.get("usage", {}).get("total_tokens", 0)

                    ai_result["input_summary"] = {
                        "markets_count": len(markets),
                        "data_sources": strategy.data_sources or {},
                        "market_filter_days": strategy.market_filter_days,
                    }

                    if not ai_result.get("market_id") and markets:
                        ai_result["market_id"] = markets[0].get("id", "")
                        ai_result["symbol"] = markets[0].get("symbol", "")

                    logger.info("AI analysis completed: %s %s @ %.2f", ai_result.get('action'), ai_result.get('side'), ai_result.get('confidence'))
                    return ai_result

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        wait = 2 ** attempt
                        logger.warning("AI API rate limited (429), retrying in %ds...", wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.error("AI API call failed: %s", e)
                    return self._build_factor_fallback(strategy, markets)
                except Exception as e:
                    logger.error("AI API call failed: %s", e)
                    return self._build_factor_fallback(strategy, markets)

    def _build_factor_fallback(self, strategy: Strategy, markets: list[dict]) -> Optional[dict]:
        """Build AI result from quantitative factor scores when AI API is unavailable."""
        if not markets:
            return None

        # Use strategy filter config for min_confidence
        filter_config = strategy.filters if isinstance(strategy.filters, dict) else {}
        min_confidence = filter_config.get('min_confidence', 40) / 100

        best = max(markets, key=lambda m: m.get("_factor_score", 0))
        factor_decision = best.get("_factor_decision", "hold")
        if factor_decision not in ("buy", "strong_buy"):
            return None

        price = best.get("_current_price", best.get("price", 0.5))
        side = best.get("_side", "yes")
        confidence = min(0.95, max(min_confidence, best.get("_factor_score", 0.5)))
        stop_loss = best.get("_factor_stop_loss")
        take_profit = best.get("_factor_take_profit")
        reasoning_lines = best.get("_factor_reasoning", [])

        risk_reward = None
        if stop_loss and take_profit and price:
            risk = price - stop_loss
            if risk > 0:
                risk_reward = round((take_profit - price) / risk, 2)

        return {
            "action": "buy",
            "side": side,
            "confidence": round(confidence, 2),
            "reasoning": "Factor fallback: " + "; ".join(reasoning_lines) if reasoning_lines else "Factor fallback decision due to AI unavailability",
            "thinking": "AI unavailable (429/failure). Using quantitative factor scores as fallback.",
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
            "market_id": best.get("id", ""),
            "symbol": best.get("symbol") or best.get("question") or best.get("slug") or best.get("id", "")[:20],
            "model": "factor_fallback",
            "duration_ms": 0,
            "tokens_used": 0,
        }

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for trading."""
        return """You are a Polymarket trading expert. Analyze markets and provide trading signals.

Your task is to:
1. Analyze market data including prices, volume, and recent activity
2. Review the quantitative factor scores provided (odds bias, time decay, capital flow, etc.)
3. Identify trading opportunities based on both quantitative factors and qualitative judgment
4. Provide clear buy/sell/hold signals with confidence levels
5. Include stop-loss and take-profit recommendations

Response format (JSON):
{
  "action": "buy" | "sell" | "hold",
  "side": "yes" | "no",
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation incorporating both AI reasoning and quantitative factor analysis",
  "thinking": "your analysis process",
  "stop_loss": recommended stop loss price,
  "take_profit": recommended take profit price,
  "risk_reward": risk/reward ratio,
  "market_id": "the selected market ID",
  "symbol": "market symbol"
}

Important:
- Factor scores above 0.65 (BUY) indicate strong quantitative support
- Consider disagreeing with the quantitative model if you identify contradictory evidence
- Always provide risk management parameters (stop_loss, take_profit)
- Lower confidence for markets with mixed or weak factor scores"""

    def _get_default_api_base(self, provider_type: str) -> str:
        """Get default API base URL for provider."""
        bases = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "azure": "https://{resource}.openai.azure.com/openai/deployments/{deployment}",
        }
        return bases.get(provider_type, "https://api.openai.com/v1")

    def _build_user_prompt(
        self, strategy: Strategy, markets: list[dict], factor_results: List[Tuple[str, BuyDecisionOutput]]
    ) -> str:
        """Build user prompt with market data and factor scores."""
        # Map token_id -> factor output for enriched per-market details
        factor_map = {token_id: output for token_id, output in factor_results}

        # Default factor weights (mirror BuyStrategyConfig defaults)
        default_weights = {
            "odds_bias": 0.25,
            "time_decay": 0.15,
            "orderbook": 0.20,
            "capital_flow": 0.20,
            "information_edge": 0.10,
            "sports_momentum": 0.15,
        }

        markets_info = []
        for i, m in enumerate(markets):
            factor_lines = []
            factor_score = m.get("_factor_score", 0)
            factor_decision = m.get("_factor_decision", "unknown")
            factor_conf = m.get("_factor_confidence", 0)

            factor_lines.append(f"    Factor Decision: {factor_decision} (confidence: {factor_conf:.2f})")
            factor_lines.append(f"    Factor Score: {factor_score:.2f}")

            # Individual factor scores from BuyStrategy output
            token_id = m.get("_token_id")
            factor_output = factor_map.get(token_id) if token_id else None
            if factor_output and factor_output.signal_scores:
                scores = factor_output.signal_scores
                individual = []
                for key in ["odds_bias", "time_decay", "orderbook", "capital_flow", "information_edge", "sports_momentum"]:
                    val = scores.get(key)
                    if val is not None:
                        individual.append(f"      {key}: {val:.3f}")
                if individual:
                    factor_lines.append("    Individual Factor Scores:")
                    factor_lines.extend(individual)

                factor_lines.append("    Factor Weights:")
                for key, w in default_weights.items():
                    factor_lines.append(f"      {key}: {w:.2f}")

            # Netflow threshold based on price stage
            price = m.get("_current_price", m.get("price", 0.5))
            threshold = TriggerChecker.STAGE_THRESHOLDS[-1]["netflow"] if TriggerChecker.STAGE_THRESHOLDS else 150
            for stage in TriggerChecker.STAGE_THRESHOLDS:
                if stage["min_price"] <= price <= stage["max_price"]:
                    threshold = stage["netflow"]
                    break
            factor_lines.append(f"    Netflow Threshold: ${threshold:,.0f} (price ${price:.2f})")

            if m.get("_factor_stop_loss"):
                factor_lines.append(f"    Suggested Stop Loss: {m['_factor_stop_loss']:.3f}")
            if m.get("_factor_take_profit"):
                factor_lines.append(f"    Suggested Take Profit: {m['_factor_take_profit']:.3f}")

            markets_info.append(f"""
Market {i+1}:
- ID: {m.get('id', 'N/A')}
- Symbol: {m.get('symbol', 'N/A')}
- Question: {m.get('question', 'N/A')}
- Current Price: {m.get('_current_price', m.get('price', 'N/A'))}
- Volume 24h: ${m.get('volume', 0):,.0f}
- Liquidity: ${m.get('liquidity', 0):,.0f}
- Price Change: {m.get('_price_change', 0):.2f}%
- Netflow: {m.get('_netflow', 0):,.0f}
- Factor Analysis:
{chr(10).join(factor_lines)}
""")

        prompt = f"""Analyze the following Polymarket markets and provide a trading signal.

Strategy: {strategy.name}
Description: {strategy.description or 'N/A'}

Each market includes a quantitative factor analysis (odds bias, time decay, capital flow).
Use these factor scores as structured input to inform your decision, but apply your own judgment.

Available Markets:
{''.join(markets_info)}

{strategy.custom_prompt or ''}

Provide your analysis and trading decision in JSON format.
If you choose to buy, include stop_loss and take_profit levels.
Explain how the factor scores influenced (or contradicted) your final decision."""

        return prompt


    def _calculate_order_size(
        self, strategy: Strategy, confidence: float
    ) -> Decimal:
        """Calculate order size based on confidence."""
        min_size = float(strategy.min_order_size)
        max_size = float(strategy.max_order_size)

        order_size = min_size + (max_size - min_size) * confidence
        return Decimal(str(max(min_size, min(max_size, order_size))))

    async def _execute_order(
        self,
        db: AsyncSession,
        strategy: Strategy,
        signal_log: SignalLog,
        data_source: Optional[DataSource] = None,
    ) -> None:
        """Execute order using py-clob-client v2 and create Position record."""
        if not self.clob_client:
            logger.error("ClobClient not initialized")
            signal_log.status = "failed"
            await db.commit()
            return

        market_id = signal_log.market_id
        if not market_id:
            logger.error("No market_id in signal")
            signal_log.status = "failed"
            await db.commit()
            return

        # 1. Duplicate order check
        existing_order = await db.execute(
            select(Order).where(Order.signal_id == signal_log.signal_id)
        )
        if existing_order.scalar_one_or_none():
            logger.warning("Duplicate order for signal %s, skipping execution", signal_log.signal_id)
            signal_log.status = "rejected"
            signal_log.signal_reason = (signal_log.signal_reason or "") + " | Rejected: duplicate order"
            await db.commit()
            return

        # 2. Daily / weekly loss limit check
        if strategy.max_daily_loss is not None or strategy.max_weekly_loss is not None:
            from sqlalchemy import func
            now = datetime.utcnow()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = day_start - timedelta(days=now.weekday())

            daily_pnl_result = await db.execute(
                select(func.coalesce(func.sum(Position.realized_pnl), Decimal("0")))
                .where(
                    Position.strategy_id == strategy.id,
                    Position.status == "closed",
                    Position.closed_at >= day_start,
                )
            )
            daily_pnl = daily_pnl_result.scalar() or Decimal("0")

            weekly_pnl_result = await db.execute(
                select(func.coalesce(func.sum(Position.realized_pnl), Decimal("0")))
                .where(
                    Position.strategy_id == strategy.id,
                    Position.status == "closed",
                    Position.closed_at >= week_start,
                )
            )
            weekly_pnl = weekly_pnl_result.scalar() or Decimal("0")

            if not strategy.is_within_risk_limits(daily_pnl, weekly_pnl):
                logger.warning(
                    "Strategy %s risk limit exceeded: daily_pnl=%s weekly_pnl=%s",
                    strategy.id, daily_pnl, weekly_pnl,
                )
                signal_log.status = "rejected"
                signal_log.signal_reason = (
                    (signal_log.signal_reason or "")
                    + f" | Rejected: risk limit exceeded (daily={daily_pnl}, weekly={weekly_pnl})"
                )
                await db.commit()
                return

        try:
            # Get token_id
            token_id = await self._get_token_id(market_id, signal_log.side)
            if not token_id:
                raise ValueError(f"Token not found for side: {signal_log.side}")

            # 3. Price freshness / slippage check
            if signal_log.current_market_price and data_source and hasattr(data_source, "get_market_data"):
                md = await data_source.get_market_data(token_id)
                if md and md.yes_price > 0:
                    current_price = md.yes_price
                    signal_price = float(signal_log.current_market_price)
                    if signal_price > 0:
                        deviation = abs(current_price - signal_price) / signal_price
                        slippage = float(strategy.slippage_tolerance or Decimal("0.001"))
                        if deviation > slippage:
                            logger.warning(
                                "Price deviation %.4f > slippage %.4f for %s, rejecting order",
                                deviation, slippage, token_id,
                            )
                            signal_log.status = "rejected"
                            signal_log.signal_reason = (
                                (signal_log.signal_reason or "")
                                + f" | Rejected: price deviation {deviation:.4f} > slippage {slippage:.4f}"
                            )
                            await db.commit()
                            return

            # Execute via official py_clob_client_v2 market order API
            from py_clob_client_v2 import MarketOrderArgs, OrderType, PartialCreateOrderOptions
            from py_clob_client_v2.order_builder.constants import BUY, SELL

            order_side = BUY if signal_log.side == "yes" else SELL
            eval_price = float(signal_log.current_market_price or 0.5)
            tick = 0.01
            if order_side == BUY:
                # Buy at or slightly above market to ensure immediate fill
                limit_price = min(0.99, round(eval_price + tick, 2))
            else:
                # Sell at or slightly below market to ensure immediate fill
                limit_price = max(0.01, round(eval_price - tick, 2))

            # MarketOrderArgs: amount is dollar amount for BUY, shares for SELL
            if order_side == BUY:
                market_amount = float(signal_log.size)
            else:
                market_amount = round(float(signal_log.size) / limit_price, 2)
                if market_amount < 0.01:
                    market_amount = 0.01

            order_args = MarketOrderArgs(
                token_id=token_id,
                side=order_side,
                amount=market_amount,
                price=limit_price,
            )
            options = PartialCreateOrderOptions(tick_size="0.01", neg_risk=False)

            # Build market order payload and post (IOC = Immediate Or Cancel)
            result = await asyncio.to_thread(
                self.clob_client.create_and_post_market_order,
                order_args,
                options,
                OrderType.IOC,
            )

            if result is None:
                raise ValueError("create_and_post_market_order returned None")

            # Normalize result to dict
            result_dict = None
            if isinstance(result, dict):
                result_dict = result
            elif hasattr(result, "__dict__"):
                result_dict = result.__dict__
            elif hasattr(result, "to_dict"):
                result_dict = result.to_dict()
            else:
                raise ValueError(f"Unexpected result type: {type(result)}")

            # Check API-level error (non-version-mismatch errors that didn't raise)
            error_val = result_dict.get("error")
            if error_val:
                raise ValueError(f"CLOB API returned error: {error_val}")

            # Extract order fields from various possible response shapes
            exchange_order_id = None
            raw_status = ""
            raw_size = None
            raw_price = None

            # Shape 1: { "orders": [ { "orderId": "..." } ] }
            orders_list = result_dict.get("orders")
            if isinstance(orders_list, list) and orders_list:
                first = orders_list[0]
                if isinstance(first, dict):
                    exchange_order_id = first.get("orderId") or first.get("order_id") or first.get("orderID")
                    raw_status = str(first.get("status", "")).lower()
                    raw_size = first.get("size")
                    raw_price = first.get("price")

            # Shape 2: direct fields on result
            if not exchange_order_id:
                exchange_order_id = (
                    result_dict.get("orderID")
                    or result_dict.get("order_id")
                    or result_dict.get("orderId")
                    or result_dict.get("id")
                )
            if not raw_status:
                raw_status = str(result_dict.get("status", "")).lower()
            if raw_size is None:
                raw_size = result_dict.get("size")
            if raw_price is None:
                raw_price = result_dict.get("price")

            # Map CLOB status to our status
            status_map = {
                "filled": "filled",
                "matched": "filled",
                "open": "open",
                "pending": "pending",
                "partial": "partially_filled",
                "partially_filled": "partially_filled",
                "cancelled": "cancelled",
                "rejected": "rejected",
                "expired": "expired",
            }
            order_status = status_map.get(raw_status, "pending")

            # Calculate intended order size in shares
            if order_side == BUY:
                shares = Decimal(str(market_amount)) / Decimal(str(limit_price))
            else:
                shares = Decimal(str(market_amount))

            fill_size = Decimal(str(raw_size)) if raw_size is not None else Decimal("0")
            avg_fill_price = Decimal(str(raw_price)) if raw_price is not None else Decimal(str(limit_price))

            # Create Order record with REAL status and exchange_order_id
            order = Order(
                id=uuid4(),
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                signal_id=signal_log.signal_id,
                market_id=signal_log.market_id,
                symbol=signal_log.symbol or signal_log.market_id,
                side=signal_log.side,
                order_type="market",
                time_in_force="IOC",
                size=Decimal(str(shares)),
                filled_size=fill_size if order_status in ("filled", "partially_filled") else Decimal("0"),
                remaining_size=Decimal(str(shares)) - (fill_size if order_status in ("filled", "partially_filled") else Decimal("0")),
                status=order_status,
                avg_fill_price=avg_fill_price if order_status in ("filled", "partially_filled") else None,
                total_cost=(fill_size * avg_fill_price) if order_status in ("filled", "partially_filled") else Decimal("0"),
                source="signal",
                exchange_order_id=exchange_order_id,
            )
            db.add(order)

            # Only create Position if the order is actually FILLED on-chain
            if order_status == "filled":
                current_price = float(avg_fill_price) if avg_fill_price > 0 else 0.5
                # Look up market title for display
                market_title = ""
                cached_market = self._market_cache.get(signal_log.market_id or "")
                if cached_market:
                    market_title = cached_market.get("question") or cached_market.get("title") or ""
                display_symbol = signal_log.symbol or market_title or signal_log.market_id
                position = Position(
                    id=uuid4(),
                    portfolio_id=strategy.portfolio_id,
                    strategy_id=strategy.id,
                    market_id=signal_log.market_id,
                    token_id=token_id,
                    symbol=display_symbol,
                    side=signal_log.side,
                    status="open",
                    size=fill_size,
                    entry_price=avg_fill_price,
                    current_price=avg_fill_price,
                    average_entry_price=avg_fill_price,
                    stop_loss_price=signal_log.stop_loss_price,
                    take_profit_price=signal_log.take_profit_price,
                    opened_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow(),
                    source="signal",
                    signal_id=str(signal_log.signal_id),
                    position_metadata={
                        "market_name": display_symbol,
                        "title": market_title or display_symbol,
                        "outcome": signal_log.side,
                    },
                )
                db.add(position)
                await db.commit()

                # Register with flow exit system
                self._flow_exit.register_position(
                    position_id=str(position.id),
                    entry_price=current_price,
                    size=float(fill_size),
                    side="long" if signal_log.side == "yes" else "short"
                )

                # Register with sports monitor (if data_source supports it)
                data_source = self._data_source_manager._sources.get(strategy.portfolio_id)
                if data_source and hasattr(data_source, "register_sports_position"):
                    stop_loss_pct = 0.10
                    if signal_log.stop_loss_price and avg_fill_price > 0:
                        stop_loss_pct = float(
                            abs(avg_fill_price - signal_log.stop_loss_price) / avg_fill_price
                        )
                    data_source.register_sports_position(
                        position_id=str(position.id),
                        market_id=market_id,
                        entry_price=current_price,
                        stop_loss_pct=stop_loss_pct,
                        side=signal_log.side,
                    )

                logger.info(
                    "Order filled and position created: exchange_order_id=%s local_order=%s market=%s side=%s",
                    exchange_order_id, order.id, market_id, signal_log.side,
                )
            else:
                await db.commit()
                logger.info(
                    "Order placed but not filled (status=%s): exchange_order_id=%s market=%s side=%s",
                    order_status, exchange_order_id, market_id, signal_log.side,
                )

        except Exception as e:
            logger.exception("Order execution failed: %s", e)
            signal_log.status = "failed"
            await db.commit()

    async def _get_token_id(self, condition_id: str, side: str) -> Optional[str]:
        """Get token_id for specified outcome. Uses cache first, then Gamma API fallback."""
        # 1. Try cache first
        market = self._market_cache.get(condition_id)
        if market:
            for token in market.get("tokens", []):
                if token.get("outcome", "").lower() == side.lower():
                    return token.get("token_id")
            clob_ids = market.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                return clob_ids.get(side.lower())

        # 2. HTTP fallback
        try:
            async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                # Try direct lookup first
                resp = await client.get(
                    f"https://gamma-api.polymarket.com/markets/{condition_id}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    market = resp.json()
                else:
                    # Fallback: search via list endpoint
                    search_resp = await client.get(
                        "https://gamma-api.polymarket.com/markets",
                        params={"conditionIds": condition_id, "limit": 1},
                        timeout=10,
                    )
                    if search_resp.status_code == 200:
                        data = search_resp.json()
                        markets = data if isinstance(data, list) else data.get("markets", [])
                        if markets:
                            market = markets[0]
                        else:
                            return None
                    else:
                        return None

            # Update cache with this single market
            hex_cid = market.get("conditionId") or market.get("condition_id") or condition_id
            numeric_id = market.get("id")
            self._market_cache[hex_cid] = market
            if numeric_id:
                self._market_cache[str(numeric_id)] = market

            # Supplement token details if missing
            if not market.get("tokens") and numeric_id:
                tokens = await self._fetch_gamma_token_details(str(numeric_id))
                if tokens:
                    market["tokens"] = tokens

            for token in market.get("tokens", []):
                if token.get("outcome", "").lower() == side.lower():
                    tid = token.get("token_id")
                    if tid:
                        self._token_to_condition[tid] = hex_cid
                    return tid

            clob_ids = market.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                tid = clob_ids.get(side.lower())
                if tid:
                    self._token_to_condition[tid] = hex_cid
                return tid

        except Exception as e:
            logger.warning("Failed to get token_id from Gamma API: %s", e)

        return None


# Global instance
strategy_runner = StrategyRunner()
