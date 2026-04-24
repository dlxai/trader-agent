"""Strategy runner service for scheduled execution."""

import asyncio
import logging
import sys
import os
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Callable
from uuid import UUID

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

logger = logging.getLogger(__name__)

# Dedicated strategy execution logger (always flushes immediately)
_strategy_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "strategy.log")
_strategy_handler = logging.FileHandler(_strategy_log_path, encoding="utf-8")
_strategy_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
strategy_exec_logger = logging.getLogger("strategy_exec")
strategy_exec_logger.setLevel(logging.DEBUG)
if not strategy_exec_logger.handlers:
    strategy_exec_logger.addHandler(_strategy_handler)

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


class _EntryConditionAdapter:
    """Lightweight adapter to feed MarketData into EntryConditionValidator.

    EntryConditionValidator requires MarketInfoSource, LiquiditySource,
    and VolatilitySource protocol implementations. This adapter wraps
    a MarketData object so the validator can run its checks without
    additional async I/O.
    """

    def __init__(self, market_data: MarketData):
        self._md = market_data

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
        return self._md.volume or 0.0

    def get_order_book_depth(self, market_id: str) -> Dict[str, float]:
        return {"bid": 0.0, "ask": 0.0}

    def get_volatility(self, market_id: str, period: str = "24h") -> float:
        return abs(self._md.change_24h) if self._md.change_24h else 0.0

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
        self._market_cache_duration_seconds = 300  # 5 minutes

        # Token ID -> Condition ID mapping (for quick lookup)
        self._token_to_condition: Dict[str, str] = {}

        # Trigger checkers per strategy (persist cooldown state across iterations)
        self._trigger_checkers: Dict[UUID, TriggerChecker] = {}

        # Market trigger handler references per strategy (for unregister on stop)
        self._market_trigger_handlers: Dict[UUID, Callable] = {}

    def _get_cached_markets(self) -> List[dict]:
        """Return cached markets if not expired."""
        if self._market_cache_ttl and datetime.utcnow() < self._market_cache_ttl:
            return list(self._market_cache.values())
        return []

    def _cache_markets(self, markets: List[dict]) -> None:
        """Cache markets and build token->condition mapping."""
        self._market_cache.clear()
        self._token_to_condition.clear()

        for m in markets:
            cid = m.get("id") or m.get("conditionId") or m.get("condition_id", "")
            if not cid:
                continue
            self._market_cache[cid] = m

            # Build token -> condition mapping
            for token in m.get("tokens", []):
                tid = token.get("token_id") or token.get("clobTokenId", "")
                if tid:
                    self._token_to_condition[tid] = cid
            # Also check clob_token_ids dict
            clob_ids = m.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                for side, tid in clob_ids.items():
                    if tid:
                        self._token_to_condition[tid] = cid

        self._market_cache_ttl = datetime.utcnow() + timedelta(
            seconds=self._market_cache_duration_seconds
        )
        logger.info("Markets cached: %d markets, %d token mappings", len(self._market_cache), len(self._token_to_condition))

    def _get_market_yes_token_id(self, market: dict) -> Optional[str]:
        """Extract YES token_id from Gamma market dict for CLOB price lookup.

        Gamma API returns condition_id in 'id' field and CLOB token_ids in
        'tokens' or 'clob_token_ids'. We need the actual CLOB token_id for
        PriceMonitor subscription and lookup.
        """
        # Try clob_token_ids dict first
        clob_ids = market.get("clob_token_ids", {})
        if isinstance(clob_ids, dict):
            for key, tid in clob_ids.items():
                if key.lower() in ("yes", "y") and tid:
                    return tid

        # Fall back to tokens list
        for token in market.get("tokens", []):
            outcome = token.get("outcome", "")
            if outcome and outcome.lower() in ("yes", "y"):
                tid = token.get("token_id") or token.get("clobTokenId", "")
                if tid:
                    return tid

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
                        from py_clob_client.client import ClobClient

                        kwargs = {
                            "host": "https://clob.polymarket.com",
                            "key": private_key,
                            "chain_id": 137,
                        }
                        if proxy:
                            kwargs["signature_type"] = 2
                            kwargs["funder"] = proxy

                        self.clob_client = ClobClient(**kwargs)
                        api_creds = self.clob_client.create_or_derive_api_creds()
                        self.clob_client.set_api_creds(api_creds)
                        logger.info("Strategy %s: ClobClient initialized successfully", strategy_id)
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

        logger.info("Strategy %s: data source ready, starting loop task...", strategy_id)

        # Register event-driven market trigger handler for dual-window confirmation
        if hasattr(data_source, "register_market_trigger_handler"):
            handler = lambda cid, td: asyncio.create_task(
                self._on_market_trigger(strategy_id, cid, td)
            )
            self._market_trigger_handlers[strategy_id] = handler
            data_source.register_market_trigger_handler(handler)
            logger.info("Strategy %s: registered dual-window market trigger handler", strategy_id)

        task = asyncio.create_task(self._run_strategy_loop(strategy_id, data_source))
        self._tasks[strategy_id] = task
        logger.info("Strategy %s: loop task created and registered", strategy_id)

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]
            self._trigger_checkers.pop(strategy_id, None)

        # Unregister market trigger handler
        handler = self._market_trigger_handlers.pop(strategy_id, None)
        if handler:
            for source in await self._data_source_manager.get_all_sources():
                if hasattr(source, "unregister_market_trigger_handler"):
                    source.unregister_market_trigger_handler(handler)
            logger.info("Strategy %s: unregistered market trigger handler", strategy_id)

        logger.info("Strategy %s: stopped", strategy_id)

    async def _run_strategy_loop(self, strategy_id: UUID, data_source: DataSource) -> None:
        """Main strategy execution loop."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()

                if not strategy:
                    logger.warning("Strategy %s: not found in DB, exiting loop", strategy_id)
                    return

                interval = strategy.run_interval_minutes * 60
                iteration = 0
                strategy_exec_logger.info("[START] Strategy %s (%s) loop started, interval=%ds, is_active=%s, is_paused=%s",
                                          strategy_id, strategy.name, interval, strategy.is_active, strategy.is_paused)

                # --- Initial warm-up: subscribe positions + markets immediately on restart ---
                try:
                    onchain_positions = await self._sync_onchain_positions(db, strategy)
                    strategy_exec_logger.info("[WARMUP] on-chain positions: %d", len(onchain_positions))
                    onchain_token_ids = [p["token_id"] for p in onchain_positions if p.get("token_id")]
                    if onchain_token_ids and hasattr(data_source, "subscribe"):
                        await data_source.subscribe(onchain_token_ids)
                        strategy_exec_logger.info("[WARMUP] subscribed %d on-chain tokens", len(onchain_token_ids))

                    markets = await self._get_available_markets(strategy)
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

                while strategy.is_active:
                    iteration += 1
                    strategy_exec_logger.info("[ITER] %d started for strategy %s", iteration, strategy_id)
                    try:
                        # 1. Sync on-chain positions from proxy wallet
                        onchain_positions = await self._sync_onchain_positions(db, strategy)
                        strategy_exec_logger.info("[ITER] synced %d on-chain positions", len(onchain_positions))

                        # 2. Subscribe WebSocket for on-chain positions only
                        if onchain_positions:
                            onchain_token_ids = [p["token_id"] for p in onchain_positions if p.get("token_id")]
                            if onchain_token_ids and hasattr(data_source, "subscribe"):
                                try:
                                    await data_source.subscribe(onchain_token_ids)
                                except Exception as e:
                                    strategy_exec_logger.warning("[ITER] subscribe failed: %s", e)

                        # 3. Monitor existing positions (stop-loss / take-profit / flow-assisted exit)
                        await self._monitor_positions(db, strategy, data_source, onchain_positions)

                        # 4. Execute strategy to find new opportunities
                        signal_log = await self._execute_strategy(db, strategy, data_source)
                        if signal_log is None:
                            strategy_exec_logger.info("[ITER] %d ended, no signal", iteration)
                        else:
                            strategy_exec_logger.info("[ITER] %d ended, signal=%s status=%s", iteration, signal_log.signal_type, signal_log.status)

                        strategy.last_run_at = datetime.utcnow()
                        strategy.total_runs += 1
                        await db.commit()
                    except Exception as e:
                        strategy_exec_logger.error("[ITER] %d error: %s\n%s", iteration, e, traceback.format_exc())

                    strategy_exec_logger.info("[SLEEP] sleeping %ds", interval)
                    for handler in strategy_exec_logger.handlers:
                        handler.flush()
                    await asyncio.sleep(interval)
                    await db.refresh(strategy)
                    strategy_exec_logger.info("[WAKE] iteration %d resuming", iteration + 1)
        finally:
            self._tasks.pop(strategy_id, None)
            strategy_exec_logger.info("[EXIT] Strategy %s loop exited", strategy_id)

    async def _on_market_trigger(
        self, strategy_id: UUID, condition_id: str, trigger_data: Dict[str, Any]
    ) -> None:
        """Handle dual-window market trigger for a specific strategy (event-driven path)."""
        strategy_exec_logger.info(
            "[EVENT] strategy=%s market=%s short_netflow=%.2f long_netflow=%.2f",
            strategy_id,
            condition_id,
            trigger_data.get("short_window", {}).get("net_flow", 0),
            trigger_data.get("long_window", {}).get("net_flow", 0),
        )
        for handler in strategy_exec_logger.handlers:
            handler.flush()

        # Skip if strategy loop is not running
        task = self._tasks.get(strategy_id)
        if not task or task.done() or task.cancelled():
            strategy_exec_logger.info("[EVENT] strategy %s not running, skip", strategy_id)
            return

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()
                if not strategy or not strategy.is_active:
                    strategy_exec_logger.info("[EVENT] strategy %s inactive, skip", strategy_id)
                    return

                data_source = await self._data_source_manager.get_or_create_source(
                    portfolio_id=strategy.portfolio_id,
                    source_type="polymarket",
                )
                await self._evaluate_single_market(
                    db, strategy, data_source, condition_id, trigger_data
                )
        except Exception as e:
            strategy_exec_logger.error("[EVENT] error handling market trigger: %s\n%s", e, traceback.format_exc())

    async def _evaluate_single_market(
        self,
        db: AsyncSession,
        strategy: Strategy,
        data_source: DataSource,
        condition_id: str,
        trigger_data: Dict[str, Any],
    ) -> Optional[SignalLog]:
        """Evaluate a single market triggered by dual-window event (event-driven fast path).

        Skips Tier 1 pre-filter and trigger checks because the dual-window
        confirmation already guarantees meaningful activity.
        """
        strategy_exec_logger.info("[EVAL] evaluating market %s for strategy %s", condition_id, strategy.id)
        for handler in strategy_exec_logger.handlers:
            handler.flush()

        # 1. Cooldown check
        trigger_checker = self._trigger_checkers.get(strategy.id)
        if trigger_checker and not trigger_checker.check_cooldown():
            strategy_exec_logger.info("[EVAL] cooldown active, skip %s", condition_id)
            return None

        # 2. Get market metadata
        market = self._market_cache.get(condition_id)
        token_id = self._get_market_yes_token_id(market) if market else None

        if not market or not token_id:
            try:
                async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                    resp = await client.get(
                        f"https://gamma-api.polymarket.com/markets/{condition_id}",
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        market = resp.json()
                        self._market_cache[condition_id] = market
                        token_id = self._get_market_yes_token_id(market)
                        if token_id:
                            self._token_to_condition[token_id] = condition_id
            except Exception as e:
                strategy_exec_logger.warning("[EVAL] failed to fetch market %s: %s", condition_id, e)
                return None

        if not market or not token_id:
            strategy_exec_logger.warning("[EVAL] no market data for %s", condition_id)
            return None

        # Push metadata and subscribe token
        if hasattr(data_source, "update_market_meta"):
            data_source.update_market_meta(token_id, market)
        if hasattr(data_source, "subscribe"):
            try:
                await data_source.subscribe([token_id])
            except Exception:
                pass

        # 3. Get real-time price
        market_data = await data_source.get_market_data(token_id)
        if not market_data:
            strategy_exec_logger.info("[EVAL] no market data for token %s", token_id)
            return None

        # 4. SignalFilter (Tier 2: price range, dead zone, expiry)
        filter_config = {}
        if strategy.filters and isinstance(strategy.filters, dict):
            filter_config = strategy.filters
        else:
            filter_config = {
                "min_confidence": 40,
                "min_price": 0.5,
                "max_price": 0.99,
                "max_hours_to_expiry": 6,
            }
        signal_filter = SignalFilter(filter_config)

        if not signal_filter.filter_market(market_data):
            strategy_exec_logger.info("[EVAL] signal filter rejected %s", condition_id)
            return None

        # 5. Keyword filter (Tier 3)
        market_name = market.get("question", market.get("symbol", ""))
        if not signal_filter.filter_by_keywords(market_name):
            strategy_exec_logger.info("[EVAL] keyword filter rejected %s", condition_id)
            return None

        # 6. Entry condition validation (Tier 4)
        adapter = _EntryConditionAdapter(market_data)
        entry_cond_config = EntryConditionConfig(
            price_min=0.05,
            price_max=0.95,
            allow_death_zone=True,
            min_liquidity=1000.0,
            min_order_book_depth=500.0,
        )
        entry_cond_validator = EntryConditionValidator(
            market_source=adapter,
            liquidity_source=adapter,
            volatility_source=adapter,
            config=entry_cond_config,
        )
        cond_result = entry_cond_validator.validate(
            market_id=market_data.market_id or token_id,
            current_price=market_data.yes_price,
        )
        if not cond_result.can_enter:
            reason = cond_result.failed_checks[0].message if cond_result.failed_checks else str(cond_result.overall_result)
            strategy_exec_logger.info("[EVAL] entry condition rejected %s: %s", condition_id, reason)
            return None

        # 7. Activity data for factor evaluation
        activity_data = await data_source.get_activity(token_id)

        # 8. Factor evaluation (Tier 6)
        buy_config = self._get_buy_strategy_config(strategy)
        buy_strategy = BuyStrategy(
            signal_generators=[],
            risk_manager=None,
            config=buy_config,
        )
        context = self._build_market_context(market, market_data, activity_data, data_source, token_id)
        factor_output = await buy_strategy.evaluate(context)

        if factor_output.decision in (BuyDecision.PASS, BuyDecision.BLOCKED):
            strategy_exec_logger.info(
                "[EVAL] factor rejected %s: decision=%s", condition_id, factor_output.decision.value
            )
            return None

        # 9. AI analysis (Tier 7) — single market, no need for top-N
        market["_triggered"] = True
        short_avg = trigger_data.get("short_window", {}).get("avg_price", market_data.yes_price)
        market["_price_change"] = (
            abs(short_avg - market_data.yes_price) / market_data.yes_price * 100
            if market_data.yes_price > 0 else 0
        )
        market["_netflow"] = trigger_data.get("short_window", {}).get("net_flow", 0)
        market["_factor_score"] = (
            sum(factor_output.signal_scores.values()) / len(factor_output.signal_scores)
            if factor_output.signal_scores else 0
        )
        market["_factor_decision"] = factor_output.decision.value
        market["_factor_confidence"] = factor_output.confidence
        market["_factor_stop_loss"] = factor_output.stop_loss
        market["_factor_take_profit"] = factor_output.take_profit
        market["_factor_reasoning"] = factor_output.reasoning
        market["_current_price"] = market_data.yes_price

        ai_result = await self._call_ai_analysis(strategy, [market], [(token_id, factor_output)])
        if not ai_result:
            strategy_exec_logger.info("[EVAL] AI returned None for %s", condition_id)
            return None

        # 10. AI confidence filter
        confidence = ai_result.get("confidence", 0)
        min_confidence = signal_filter.min_confidence / 100
        if confidence < min_confidence:
            strategy_exec_logger.info(
                "[EVAL] AI confidence %.2f < min %.2f for %s", confidence, min_confidence, condition_id
            )
            return None

        # 11. Update trigger time
        if trigger_checker:
            trigger_checker.update_trigger_time()

        # 12. Build SignalLog
        order_size = self._calculate_order_size(strategy, confidence)
        market_id = ai_result.get("market_id", condition_id)
        symbol = ai_result.get("symbol", market.get("symbol", ""))

        signal_log = SignalLog(
            id=UUID(),
            user_id=strategy.user_id,
            portfolio_id=strategy.portfolio_id,
            strategy_id=strategy.id,
            signal_id=str(UUID()),
            signal_type=ai_result.get("action", "hold"),
            confidence=Decimal(str(ai_result.get("confidence", 0))),
            side=ai_result.get("side", "yes"),
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
        )
        db.add(signal_log)
        await db.commit()

        # 13. Position limits and execution
        action = ai_result.get("action")
        side = ai_result.get("side", "yes")

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

            await self._execute_order(db, strategy, signal_log)

        strategy_exec_logger.info(
            "[EVAL] done for %s signal_type=%s status=%s", condition_id, signal_log.signal_type, signal_log.status
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
        markets = await self._get_available_markets(strategy)
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
                'max_hours_to_expiry': 6,
            }

        signal_filter = SignalFilter(filter_config)

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
        stats = {"prefilter": 0, "no_price": 0, "signal_filter": 0, "keyword": 0, "entry_cond": 0, "no_trigger": 0, "factor_reject": 0, "passed": 0}

        for market in markets:
            condition_id = market.get("id") or market.get("conditionId") or market.get("condition_id", "")
            token_id = market_token_map.get(condition_id)
            if not token_id:
                continue

            # === Tier 1: Activity flow pre-filter (PRIMARY GATE, 60s window) ===
            activity_data = await data_source.get_activity(token_id)
            if activity_data is not None:
                # 60秒窗口：无活跃交易员且净流入不足时跳过
                if activity_data.unique_traders < 2 and abs(activity_data.netflow) < 50:
                    logger.debug(
                        "Activity pre-filter rejected %s (60s): traders=%d netflow=%.2f",
                        token_id, activity_data.unique_traders, activity_data.netflow,
                    )
                    stats["prefilter"] += 1
                    continue

            # Get real-time price data
            market_data = await data_source.get_market_data(token_id)
            if not market_data:
                stats["no_price"] += 1
                continue

            # Apply SignalFilter (price range, dead zone, expiry)
            if not signal_filter.filter_market(market_data):
                stats["signal_filter"] += 1
                continue

            # Keyword filter
            market_name = market.get("question", market.get("symbol", ""))
            if not signal_filter.filter_by_keywords(market_name):
                stats["keyword"] += 1
                continue

            # === Layer 2: Entry Condition Validation ===
            new_price = market_data.yes_price

            adapter = _EntryConditionAdapter(market_data)
            entry_cond_config = EntryConditionConfig(
                price_min=0.05,
                price_max=0.95,
                allow_death_zone=True,
                min_liquidity=1000.0,
                min_order_book_depth=500.0,
            )
            entry_cond_validator = EntryConditionValidator(
                market_source=adapter,
                liquidity_source=adapter,
                volatility_source=adapter,
                config=entry_cond_config,
            )
            cond_result = entry_cond_validator.validate(
                market_id=market_data.market_id or token_id,
                current_price=new_price,
            )
            if not cond_result.can_enter:
                failed = cond_result.failed_checks
                reason = failed[0].message if failed else str(cond_result.overall_result)
                logger.info("EntryConditionValidator rejected %s: %s", market_data.market_id, reason)
                stats["entry_cond"] += 1
                continue

            # Trigger check (price change + netflow)
            # old_price from Gamma API market dict usually has no "price" field
            raw_old_price = market.get("price")
            new_price = market_data.yes_price

            if raw_old_price is not None:
                price_triggered = trigger_checker.check_price_trigger(float(raw_old_price), new_price)
            else:
                # First-time scan: no historical price, skip price trigger requirement
                price_triggered = True
                logger.debug("Price trigger skipped for %s (first scan)", token_id)

            netflow = activity_data.netflow if activity_data else 0
            activity_triggered = trigger_checker.check_activity_trigger(netflow, new_price)

            # Default AND logic: both price and activity must confirm
            # If no activity data available, skip activity trigger requirement
            should_trigger = price_triggered and (activity_triggered if activity_data is not None else True)

            # Sports event override: strong game events can bypass the AND gate
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
            # Build MarketContext and run BuyStrategy.evaluate()
            context = self._build_market_context(market, market_data, activity_data, data_source, token_id)
            factor_output = await self._buy_strategy.evaluate(context)

            # Filter by factor score: PASS or BLOCKED skip
            if factor_output.decision in (BuyDecision.PASS, BuyDecision.BLOCKED):
                stats["factor_reject"] += 1
                continue

            # Store factor result
            factor_results.append((token_id, factor_output))

            # Enrich market with trigger and factor info for AI
            market["_triggered"] = True
            raw_old_price = market.get("price")
            old_price = float(raw_old_price) if raw_old_price is not None else new_price
            market["_price_change"] = abs(new_price - old_price) / old_price * 100 if old_price > 0 else 0
            market["_netflow"] = netflow
            market["_factor_score"] = sum(factor_output.signal_scores.values()) / len(factor_output.signal_scores) if factor_output.signal_scores else 0
            market["_factor_decision"] = factor_output.decision.value
            market["_factor_confidence"] = factor_output.confidence
            market["_factor_stop_loss"] = factor_output.stop_loss
            market["_factor_take_profit"] = factor_output.take_profit
            market["_factor_reasoning"] = factor_output.reasoning
            market["_current_price"] = new_price

            triggered_markets.append(market)

        strategy_exec_logger.info(
            "[FILTER] total=%d prefilter=%d no_price=%d signal_filter=%d keyword=%d entry_cond=%d no_trigger=%d factor_reject=%d passed=%d",
            len(markets), stats["prefilter"], stats["no_price"], stats["signal_filter"], stats["keyword"], stats["entry_cond"], stats["no_trigger"], stats["factor_reject"], stats["passed"],
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

        signal_log = SignalLog(
            id=UUID(),
            user_id=strategy.user_id,
            portfolio_id=strategy.portfolio_id,
            strategy_id=strategy.id,
            signal_id=str(UUID()),
            signal_type=ai_result.get("action", "hold"),
            confidence=Decimal(str(ai_result.get("confidence", 0))),
            side=ai_result.get("side", "yes"),
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
        )

        db.add(signal_log)
        await db.commit()

        # 12. Position limits check before execution
        action = ai_result.get("action")
        side = ai_result.get("side", "yes")

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
            await self._execute_order(db, strategy, signal_log)

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
            # ClobClient v2 has no get_positions() — use HTTP directly
            import httpx

            api_key = getattr(getattr(self.clob_client, "creds", None), "api_key", None)
            if not api_key:
                logger.warning("No API key available for positions fetch")
                return []
            headers = {"POLYMARKET_API_KEY": api_key}
            async with httpx.AsyncClient(timeout=15.0, proxy=self._proxy_url) as client:
                resp = await client.get(
                    "https://clob.polymarket.com/positions",
                    headers=headers,
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
                        id=UUID(),
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

            from py_clob_client.clob_types import MarketOrderArgs
            from py_clob_client.order_builder.constants import SELL

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=float(position.size),
                side=SELL,
            )

            signed_order = await asyncio.to_thread(
                self.clob_client.create_market_order, order_args
            )
            result = await asyncio.to_thread(
                self.clob_client.post_order, signed_order
            )

            # Update position
            exit_price = Decimal(str(current_price))
            position.close_position(exit_price, datetime.utcnow())
            position.notes = f"Closed by strategy: {reason}"

            # Create closing order record
            close_order = Order(
                id=UUID(),
                user_id=strategy.user_id,
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                position_id=position.id,
                market_id=position.market_id,
                symbol=position.symbol,
                side=position.side,
                order_type="market",
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
                id=UUID(),
                user_id=strategy.user_id,
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                signal_id=str(UUID()),
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

    async def _get_available_markets(self, strategy: Strategy) -> list[dict]:
        """Fetch available markets from Gamma API with caching."""
        # 1. Try cache first
        cached = self._get_cached_markets()
        if cached:
            logger.info("Using cached markets: %d markets", len(cached))
            return cached

        # 2. Fetch from Gamma API
        try:
            async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={
                        "active": "true",
                        "archived": "false",
                        "closed": "false",
                        "limit": 100,
                        "order": "volume",
                        "ascending": "false",
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

            markets = data if isinstance(data, list) else data.get("markets", [])
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

            # 3. Cache and build mappings
            self._cache_markets(filtered)
            logger.info("Fetched %d markets from Gamma API", len(filtered))
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
            buy_threshold=params.get("buy_threshold", 0.65),
            hold_threshold=params.get("hold_threshold", 0.45),
            max_single_position_pct=float(strategy.max_position_size) / 100
            if strategy.max_position_size and strategy.max_position_size > 0
            else 0.10,
            max_total_positions=strategy.max_positions or 20,
            min_liquidity=float(strategy.min_liquidity) if strategy.min_liquidity else 10000.0,
        )

    def _build_market_context(
        self,
        market: dict,
        market_data: MarketData,
        activity_data: Optional[ActivityData],
        data_source: DataSource,
        token_id: str,
    ) -> BuyMarketContext:
        """Build BuyStrategy MarketContext from available data."""
        current_price = market_data.yes_price

        # 1. Odds Bias: distance from 0.5 implies conviction
        distance_from_mid = abs(current_price - 0.5)
        odds_bias = OddsBiasMetrics(
            implied_probability=current_price,
            estimated_true_probability=min(1.0, max(0.0, current_price + (current_price - 0.5) * 0.1)),
            edge=distance_from_mid * 0.15,
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
                capital_flow = CapitalFlowMetrics(
                    smart_money_flow=min(1.0, max(-1.0, net_ratio * 2)),
                    retail_flow=0.0,
                    institutional_flow=0.0,
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

        return BuyMarketContext(
            market_id=market.get("id", ""),
            outcome_id=market.get("token_id", ""),
            current_price=current_price,
            current_odds=current_price,
            timestamp=datetime.utcnow(),
            volume_24h=market_data.volume or market.get("volume", 0),
            liquidity=market.get("liquidity", 0),
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

        # Get Provider config
        provider = None
        if strategy.provider_id:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Provider).where(Provider.id == strategy.provider_id)
                )
                provider = result.scalar_one_or_none()

        if not provider or not provider.api_key:
            logger.warning("No provider or API key found for strategy %s", strategy.id)
            return self._generate_mock_ai_result(markets)

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

        except Exception as e:
            logger.error("AI API call failed: %s", e)
            return self._generate_mock_ai_result(markets)

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
        markets_info = []
        for i, m in enumerate(markets):
            factor_lines = []
            factor_score = m.get("_factor_score", 0)
            factor_decision = m.get("_factor_decision", "unknown")
            factor_conf = m.get("_factor_confidence", 0)

            factor_lines.append(f"    Factor Decision: {factor_decision} (confidence: {factor_conf:.2f})")
            factor_lines.append(f"    Factor Score: {factor_score:.2f}")

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

    def _generate_mock_ai_result(self, markets: list[dict]) -> dict:
        """Generate mock AI result for testing."""
        if not markets:
            return {
                "action": "hold",
                "side": "yes",
                "confidence": 0.0,
                "reasoning": "No markets available",
                "thinking": "No markets match the filter criteria",
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "model": "mock",
                "duration_ms": 0,
                "tokens_used": 0,
            }

        import random
        market = random.choice(markets)
        price = market.get("_current_price", market.get("price", 0.5))

        actions = ["buy", "sell", "hold"]
        action = random.choice(actions)
        side = "yes" if random.random() > 0.5 else "no"
        confidence = round(random.uniform(0.3, 0.9), 2)

        return {
            "action": action if action != "hold" else "hold",
            "side": side,
            "confidence": confidence,
            "reasoning": f"Mock analysis: Price at {price}, confidence {confidence}",
            "thinking": "This is a mock result for testing purposes",
            "stop_loss": round(price * 0.9, 2) if action == "buy" else round(price * 1.1, 2),
            "take_profit": round(price * 1.2, 2) if action == "buy" else round(price * 0.8, 2),
            "risk_reward": 2.0,
            "market_id": market.get("id", ""),
            "symbol": market.get("symbol", ""),
            "model": "mock",
            "duration_ms": 100,
            "tokens_used": 50,
        }

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
    ) -> None:
        """Execute order using py-clob-client v2 and create Position record."""
        if not self.clob_client:
            logger.error("ClobClient not initialized")
            return

        market_id = signal_log.market_id
        if not market_id:
            logger.error("No market_id in signal")
            return

        try:
            # Get token_id
            token_id = await self._get_token_id(market_id, signal_log.side)
            if not token_id:
                logger.warning("Token not found for side: %s", signal_log.side)
                return

            # Execute market order
            from py_clob_client.clob_types import MarketOrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL

            order_side = BUY if signal_log.side == "yes" else SELL
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=float(signal_log.size),
                side=order_side,
            )

            signed_order = await asyncio.to_thread(
                self.clob_client.create_market_order, order_args
            )
            result = await asyncio.to_thread(
                self.clob_client.post_order, signed_order
            )

            fill_size = Decimal(str(result.get("size", signal_log.size)))
            avg_price = signal_log.size and (Decimal(str(result.get("price", signal_log.size))) / signal_log.size) or Decimal("0")
            # Use a simpler avg_fill_price estimate if not directly available
            avg_fill_price = Decimal(str(result.get("price", 0))) or signal_log.stop_loss_price or Decimal("0.5")

            # Create Order record
            order = Order(
                id=UUID(),
                user_id=strategy.user_id,
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                signal_id=signal_log.signal_id,
                market_id=signal_log.market_id,
                symbol=signal_log.side,
                side=signal_log.side,
                order_type="market",
                size=signal_log.size,
                filled_size=fill_size,
                remaining_size=signal_log.size - fill_size,
                status="filled",
                avg_fill_price=avg_fill_price,
                total_cost=fill_size * avg_fill_price,
                source="signal",
            )
            db.add(order)

            # Create Position record for tracking
            current_price = float(avg_fill_price) if avg_fill_price > 0 else 0.5
            position = Position(
                id=UUID(),
                portfolio_id=strategy.portfolio_id,
                strategy_id=strategy.id,
                market_id=signal_log.market_id,
                symbol=signal_log.symbol or signal_log.market_id,
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

            logger.info("Order placed and position created: %s, market=%s, side=%s", position.id, market_id, signal_log.side)

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
                resp = await client.get(
                    f"https://gamma-api.polymarket.com/markets/{condition_id}",
                    timeout=10,
                )
                resp.raise_for_status()
                market = resp.json()

            # Update cache with this single market
            self._market_cache[condition_id] = market

            for token in market.get("tokens", []):
                if token.get("outcome", "").lower() == side.lower():
                    tid = token.get("token_id")
                    if tid:
                        self._token_to_condition[tid] = condition_id
                    return tid

            clob_ids = market.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                tid = clob_ids.get(side.lower())
                if tid:
                    self._token_to_condition[tid] = condition_id
                return tid

        except Exception as e:
            logger.warning("Failed to get token_id from Gamma API: %s", e)

        return None


# Global instance
strategy_runner = StrategyRunner()
