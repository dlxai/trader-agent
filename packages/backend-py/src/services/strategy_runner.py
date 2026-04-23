"""Strategy runner service for scheduled execution."""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    CapitalFlowMetrics,
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
        print(f"Markets cached: {len(self._market_cache)} markets, {len(self._token_to_condition)} token mappings")

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        if strategy_id in self._tasks:
            return  # Already running

        # Get strategy and portfolio info from database
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()
            if not strategy or not strategy.portfolio_id:
                raise ValueError("Strategy not found or no portfolio")

            # Initialize ClobClient v2 if not already done
            if not self.clob_client:
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

                if not private_key:
                    raise ValueError("No default wallet with private key found")

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
                except Exception as e:
                    print(f"Failed to initialize ClobClient: {e}")
                    raise

        # Get or create shared data source (starts WebSocket connections)
        data_source = await self._data_source_manager.get_or_create_source(
            portfolio_id=strategy.portfolio_id,
            source_type="polymarket"
        )

        print(f"Strategy {strategy_id}: data source started, WebSocket connections active")

        task = asyncio.create_task(self._run_strategy_loop(strategy_id, data_source))
        self._tasks[strategy_id] = task

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]

    async def _run_strategy_loop(self, strategy_id: UUID, data_source: DataSource) -> None:
        """Main strategy execution loop."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                return

            interval = strategy.run_interval_minutes * 60

            while strategy.is_active:
                try:
                    # 1. Sync on-chain positions from proxy wallet
                    onchain_positions = await self._sync_onchain_positions(db, strategy)

                    # 2. Subscribe WebSocket for on-chain positions only
                    if onchain_positions:
                        onchain_token_ids = [p["token_id"] for p in onchain_positions if p.get("token_id")]
                        if onchain_token_ids and hasattr(data_source, "subscribe"):
                            try:
                                await data_source.subscribe(onchain_token_ids)
                            except Exception as e:
                                print(f"Failed to subscribe on-chain positions: {e}")

                    # 3. Monitor existing positions (stop-loss / take-profit / flow-assisted exit)
                    await self._monitor_positions(db, strategy, data_source, onchain_positions)

                    # 4. Execute strategy to find new opportunities
                    await self._execute_strategy(db, strategy, data_source)

                    strategy.last_run_at = datetime.utcnow()
                    strategy.total_runs += 1
                    await db.commit()
                except Exception as e:
                    print(f"Strategy execution error: {e}")
                    import traceback
                    traceback.print_exc()

                await asyncio.sleep(interval)
                await db.refresh(strategy)

    async def _execute_strategy(
        self, db: AsyncSession, strategy: Strategy, data_source: DataSource
    ) -> Optional[SignalLog]:
        """Execute strategy once: filter -> factor evaluation -> AI decision -> order."""

        # 1. Get available markets
        markets = await self._get_available_markets(strategy)
        if not markets:
            return None

        # 2. Initialize filter and trigger
        filter_config = {}
        if strategy.filters:
            filter_config = strategy.filters if isinstance(strategy.filters, dict) else {}
        elif strategy.position_monitor:
            filter_config = {
                'min_confidence': 40,
                'min_price': 0.5,
                'max_price': 0.99,
                'max_hours_to_expiry': 6,
            }

        signal_filter = SignalFilter(filter_config)

        trigger_config = {}
        if strategy.trigger:
            trigger_config = strategy.trigger if isinstance(strategy.trigger, dict) else {}

        trigger_checker = TriggerChecker(trigger_config)

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

        # 5. Subscribe token_ids to data source for real-time updates
        token_ids = [m.get("id") or m.get("token_id") for m in markets if m.get("id") or m.get("token_id")]
        if token_ids and hasattr(data_source, "subscribe"):
            try:
                await data_source.subscribe(token_ids)
                print(f"Subscribed {len(token_ids)} tokens to data source")
            except Exception as e:
                print(f"Failed to subscribe tokens: {e}")

        # 6. Filter markets + check triggers + factor evaluation
        triggered_markets: List[dict] = []
        factor_results: List[Tuple[str, BuyDecisionOutput]] = []

        for market in markets:
            token_id = market.get("id") or market.get("token_id")
            if not token_id:
                continue

            # Get real-time price data
            market_data = await data_source.get_market_data(token_id)
            if not market_data:
                continue

            # Apply SignalFilter (price range, dead zone, expiry)
            if not signal_filter.filter_market(market_data):
                continue

            # Keyword filter
            market_name = market.get("question", market.get("symbol", ""))
            if not signal_filter.filter_by_keywords(market_name):
                continue

            # === Layer 3: Entry Condition Validation ===
            new_price = market_data.yes_price

            # EntryConditionValidator (price range, liquidity, expiry, volatility)
            adapter = _EntryConditionAdapter(market_data)
            entry_cond_config = EntryConditionConfig(
                price_min=0.05,
                price_max=0.95,
                death_zone_min=0.60,
                death_zone_max=0.85,
                allow_death_zone=False,
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
                print(f"EntryConditionValidator rejected {market_data.market_id}: {reason}")
                continue

            # Trigger check (price change + netflow)
            old_price = market.get("price", 0.5)
            new_price = market_data.yes_price

            price_triggered = trigger_checker.check_price_trigger(old_price, new_price)

            activity_data = await data_source.get_activity(token_id)
            netflow = activity_data.netflow if activity_data else 0
            activity_triggered = trigger_checker.check_activity_trigger(netflow, new_price)

            if not (price_triggered or activity_triggered):
                continue

            # === Factor Evaluation ===
            # Build MarketContext and run BuyStrategy.evaluate()
            context = self._build_market_context(market, market_data, activity_data)
            factor_output = await self._buy_strategy.evaluate(context)

            # Filter by factor score: PASS or BLOCKED skip
            if factor_output.decision in (BuyDecision.PASS, BuyDecision.BLOCKED):
                continue

            # Store factor result
            factor_results.append((token_id, factor_output))

            # Enrich market with trigger and factor info for AI
            market["_triggered"] = True
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

        if not triggered_markets:
            return None

        # Sort by factor score descending, take top candidates
        triggered_markets.sort(key=lambda m: m.get("_factor_score", 0), reverse=True)
        top_markets = triggered_markets[:5]  # Send top 5 to AI

        # 6. Call AI analysis with factor scores as context
        ai_result = await self._call_ai_analysis(strategy, top_markets, factor_results)
        if not ai_result:
            return None

        # 7. AI confidence filter
        confidence = ai_result.get("confidence", 0)
        min_confidence = signal_filter.min_confidence / 100
        if confidence < min_confidence:
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
                print(f"Signal rejected: max positions {current_positions}/{strategy.max_positions}")
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
                print(f"Signal rejected: duplicate position {market_id} {side}")
                return signal_log

            # Execute order
            await self._execute_order(db, strategy, signal_log)

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
            # Get positions from CLOB v2 API (sync call wrapped in to_thread)
            raw_positions = await asyncio.to_thread(
                lambda: self.clob_client.get_positions()
            )

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
                    print(f"On-chain position synced: {ocp['market_id']} {ocp['side']} size={ocp['size']}")

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
                    print(f"Position closed (not on-chain): {dbp.id} {dbp.market_id} {dbp.side}")
                    # Unregister from sports monitor
                    if data_source and hasattr(data_source, "unregister_sports_position"):
                        data_source.unregister_sports_position(str(dbp.id))

            await db.commit()
            return onchain_list

        except Exception as e:
            print(f"On-chain position sync failed: {e}")
            import traceback
            traceback.print_exc()
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
                print(f"Subscribed {len(onchain_token_ids)} on-chain position tokens to WebSocket")
            except Exception as e:
                print(f"Failed to subscribe on-chain position tokens: {e}")

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
                print(f"Position monitoring error for {pos.id}: {e}")
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
            print("ClobClient not initialized, cannot close position")
            return

        try:
            # Get token_id for the position's side
            token_id = await self._get_token_id(position.market_id, position.side)
            if not token_id:
                print(f"Token not found for position {position.id}")
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

            print(f"Position closed: {position.id}, reason={reason}, pnl={position.realized_pnl}")

        except Exception as e:
            print(f"Close position failed for {position.id}: {e}")
            import traceback
            traceback.print_exc()

    async def _get_available_markets(self, strategy: Strategy) -> list[dict]:
        """Fetch available markets from Gamma API with caching."""
        # 1. Try cache first
        cached = self._get_cached_markets()
        if cached:
            print(f"Using cached markets: {len(cached)} markets")
            return cached

        # 2. Fetch from Gamma API
        try:
            async with httpx.AsyncClient() as client:
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
            filtered = [m for m in markets if m.get("active") and m.get("volume", 0) > 1000]

            # 3. Cache and build mappings
            self._cache_markets(filtered)
            return filtered

        except Exception as e:
            print(f"Failed to fetch markets from Gamma API: {e}")
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
        activity_data: Optional[ActivityData]
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

        # 3. Capital Flow from activity data
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
            orderbook_pressure=None,  # No orderbook data yet
            capital_flow=capital_flow,
            information_edge=None,     # No news/social data yet
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
            print(f"No provider or API key found for strategy {strategy.id}")
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
            async with httpx.AsyncClient(timeout=60.0) as client:
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

            print(f"AI analysis completed: {ai_result.get('action')} {ai_result.get('side')} @ {ai_result.get('confidence')}")
            return ai_result

        except Exception as e:
            print(f"AI API call failed: {e}")
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
            print("ClobClient not initialized")
            return

        market_id = signal_log.market_id
        if not market_id:
            print("No market_id in signal")
            return

        try:
            # Get token_id
            token_id = await self._get_token_id(market_id, signal_log.side)
            if not token_id:
                print(f"Token not found for side: {signal_log.side}")
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

            print(f"Order placed and position created: {position.id}, market={market_id}, side={signal_log.side}")

        except Exception as e:
            print(f"Order execution failed: {e}")
            import traceback
            traceback.print_exc()
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
            async with httpx.AsyncClient() as client:
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
            print(f"Failed to get token_id from Gamma API: {e}")

        return None


# Global instance
strategy_runner = StrategyRunner()
