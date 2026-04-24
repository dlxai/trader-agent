"""Position monitor for stop-loss and take-profit - real-time monitoring."""

import asyncio
import os
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional, Dict, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.position import Position
from src.models.order import Order
from src.models.wallet import Wallet
from src.models.portfolio import Portfolio
from src.core.crypto import decrypt_private_key
from src.services.data_source_manager import get_data_source_manager, DataSource


class PositionMonitor:
    """Monitor positions for stop-loss and take-profit triggers.

    Real-time monitoring via WebSocket price updates.
    - Every 60s: sync on-chain positions to local DB
    - Every 60s: subscribe position token_ids to DataSource WebSocket
    - Real-time: check stop-loss/take-profit when WebSocket price updates
    """

    def __init__(self):
        self._running = False
        self._sync_interval = 60  # Sync every 60 seconds
        self._data_source: Optional[DataSource] = None
        self._clob_client = None  # ClobClient for fetching positions
        self._portfolio_id: Optional[UUID] = None
        self._position_cache: Dict[str, Position] = {}  # token_id -> Position
        self._wallet_address: Optional[str] = None  # Wallet address for API calls
        self._proxy_wallet_address: Optional[str] = None  # Proxy wallet address for position queries
        self._proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None

    async def start(self) -> None:
        """Start the position monitor."""
        self._running = True

        # 获取活跃钱包
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Wallet).where(Wallet.is_active == True).limit(1)
            )
            wallet = result.scalar_one_or_none()

            if not wallet:
                print("No active wallet found, position monitor not started")
                return

            # 解密私钥
            private_key_raw = wallet.private_key_encrypted if wallet else None
            private_key = decrypt_private_key(private_key_raw) if private_key_raw else None
            proxy_wallet_address = wallet.proxy_wallet_address if wallet else None
            self._proxy_wallet_address = proxy_wallet_address
            self._wallet_address = wallet.address if wallet else None

            # 获取默认 portfolio
            result = await db.execute(
                select(Portfolio).where(Portfolio.user_id == wallet.user_id).limit(1)
            )
            portfolio = result.scalar_one_or_none()

            if not portfolio:
                print("No portfolio found, position monitor not started")
                return

            self._portfolio_id = portfolio.id

            # 初始化 ClobClient 用于获取持仓
            try:
                from py_clob_client.client import ClobClient
                kwargs = {
                    "host": "https://clob.polymarket.com",
                    "key": private_key,
                    "chain_id": 137,
                }
                if proxy_wallet_address:
                    kwargs["signature_type"] = 2
                    kwargs["funder"] = proxy_wallet_address

                self._clob_client = ClobClient(**kwargs)
                api_creds = self._clob_client.create_or_derive_api_creds()
                self._clob_client.set_api_creds(api_creds)
            except Exception as e:
                print(f"Failed to initialize ClobClient: {e}")
                return

            # 创建 DataSource 用于 WebSocket 订阅价格（可选，失败不影响持仓同步）
            try:
                self._data_source = await get_data_source_manager().get_or_create_source(
                    portfolio_id=self._portfolio_id,
                    source_type="polymarket",
                )
            except Exception as e:
                print(f"DataSource creation failed (WebSocket monitoring disabled): {e}")
                self._data_source = None

        asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the position monitor."""
        self._running = False
        self._clob_client = None
        if self._data_source:
            await get_data_source_manager().remove_source(self._portfolio_id)
        self._data_source = None

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - runs every 60s."""
        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    # 1. 同步链上持仓到本地数据库
                    await self._sync_positions_from_chain(db)

                    # 2. 订阅持仓 token_ids 到 WebSocket
                    await self._subscribe_positions(db)

                    # 3. 用缓存的价格检查止损/止盈（实时触发在 on_price_update 里）
                    await self._check_all_positions(db)
            except Exception as e:
                print(f"Position monitor error: {e}")

            await asyncio.sleep(self._sync_interval)

    async def _sync_positions_from_chain(self, db: AsyncSession) -> None:
        """从 Polymarket 链上同步持仓到本地数据库."""
        from uuid import uuid4
        import httpx

        # 使用 data-api.polymarket.com 获取持仓
        if not self._clob_client:
            return

        try:
            # 获取 proxy wallet 地址（Polymarket 持仓在 proxy 地址下）
            address = self._proxy_wallet_address or self._wallet_address
            if not address:
                return

            # 调用 data-api.polymarket.com
            async with httpx.AsyncClient(proxy=self._proxy_url) as client:
                resp = await client.get(
                    "https://data-api.polymarket.com/positions",
                    params={
                        "sizeThreshold": "1",
                        "limit": "100",
                        "sortBy": "TOKENS",
                        "sortDirection": "DESC",
                        "user": address,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

            if not data:
                return

            positions_list = data if isinstance(data, list) else data.get("positions", [])
            if not isinstance(positions_list, list):
                return

            # 规范化持仓数据
            onchain_list = []
            for p in positions_list:
                if not isinstance(p, dict):
                    continue
                size = float(p.get("size") or p.get("quantity") or 0)
                if size <= 0:
                    continue

                token_id = p.get("tokenId") or p.get("token_id") or ""
                market_id = p.get("conditionId") or p.get("marketId") or ""
                title = p.get("title") or p.get("question") or p.get("marketName") or p.get("market") or ""
                outcome = p.get("outcome") or p.get("position") or ""
                side = (p.get("side") or "BUY").lower()
                if side in ("buy", "BUY"):
                    side = "yes"
                elif side in ("sell", "SELL"):
                    side = "no"
                else:
                    side = "yes"

                onchain_list.append({
                    "token_id": token_id,
                    "market_id": market_id,
                    "title": title,
                    "outcome": outcome,
                    "side": side,
                    "size": Decimal(str(size)),
                    "avg_price": float(p.get("avgCost") or p.get("avgPrice") or p.get("avg_cost") or 0.5),
                    "unrealized_pnl": float(p.get("unrealizedPnl") or p.get("unrealized_pnl") or 0),
                })

            if not onchain_list:
                # 链上无持仓，关闭所有本地 open 持仓
                result = await db.execute(
                    select(Position).where(
                        Position.portfolio_id == self._portfolio_id,
                        Position.status == "open"
                    )
                )
                for pos in result.scalars().all():
                    pos.status = "closed"
                    pos.closed_at = datetime.utcnow()
                await db.commit()
                self._position_cache.clear()
                return

            # 获取本地已有的持仓
            result = await db.execute(
                select(Position).where(Position.portfolio_id == self._portfolio_id)
            )
            local_positions = {(p.token_id, p.side): p for p in result.scalars().all()}
            onchain_keys = set()

            # 更新或创建持仓
            for ocp in onchain_list:
                key = (ocp["token_id"], ocp["side"])
                onchain_keys.add(key)

                display_name = ocp.get("title") or ocp.get("outcome") or (ocp["market_id"][:50] if ocp["market_id"] else "unknown")
                avg_price = Decimal(str(ocp["avg_price"]))
                size = ocp["size"]
                unrealized = Decimal(str(ocp["unrealized_pnl"]))
                # Derive current price from cost basis + unrealized PnL
                if size > 0:
                    current_price = avg_price + (unrealized / size)
                else:
                    current_price = avg_price
                # Compute PnL percent
                cost_basis = avg_price * size
                if cost_basis > 0:
                    pnl_percent = (unrealized / cost_basis) * Decimal("100")
                else:
                    pnl_percent = Decimal("0")

                if key in local_positions:
                    # 更新已有持仓
                    local_pos = local_positions[key]
                    local_pos.size = size
                    local_pos.entry_price = avg_price
                    local_pos.current_price = current_price
                    local_pos.average_entry_price = avg_price
                    local_pos.unrealized_pnl = unrealized
                    local_pos.total_pnl = unrealized
                    local_pos.pnl_percent = pnl_percent
                    local_pos.last_updated_at = datetime.utcnow()
                    if display_name:
                        local_pos.symbol = display_name
                        meta = local_pos.position_metadata or {}
                        meta["market_name"] = display_name
                        local_pos.position_metadata = meta
                    # 更新缓存
                    if ocp["token_id"]:
                        self._position_cache[ocp["token_id"]] = local_pos
                else:
                    # 创建新持仓
                    new_pos = Position(
                        id=uuid4(),
                        portfolio_id=self._portfolio_id,
                        token_id=ocp["token_id"],
                        market_id=ocp["market_id"],
                        symbol=display_name,
                        side=ocp["side"],
                        status="open",
                        size=size,
                        entry_price=avg_price,
                        current_price=current_price,
                        average_entry_price=avg_price,
                        realized_pnl=Decimal("0"),
                        unrealized_pnl=unrealized,
                        total_pnl=unrealized,
                        pnl_percent=pnl_percent,
                        opened_at=datetime.utcnow(),
                        last_updated_at=datetime.utcnow(),
                        source="chain_sync",
                        position_metadata={
                            "token_id": ocp["token_id"],
                            "market_name": display_name,
                        },
                    )
                    db.add(new_pos)
                    if ocp["token_id"]:
                        self._position_cache[ocp["token_id"]] = new_pos

            # 关闭链上已平仓但本地还显示开的持仓
            for key, local_pos in local_positions.items():
                if key not in onchain_keys and local_pos.status == "open":
                    local_pos.status = "closed"
                    local_pos.closed_at = datetime.utcnow()
                    # 从缓存移除
                    if local_pos.token_id and local_pos.token_id in self._position_cache:
                        del self._position_cache[local_pos.token_id]

            await db.commit()

        except Exception as e:
            print(f"Failed to sync positions from chain: {e}")

    async def _subscribe_positions(self, db: AsyncSession) -> None:
        """订阅持仓 token_ids 到 WebSocket."""
        if not self._data_source:
            return

        try:
            # 获取本地 open 持仓的 token_ids
            result = await db.execute(
                select(Position).where(
                    Position.portfolio_id == self._portfolio_id,
                    Position.status == "open",
                    Position.token_id.isnot(None),
                )
            )
            positions = result.scalars().all()
            token_ids = [p.token_id for p in positions if p.token_id]

            if token_ids:
                await self._data_source.subscribe(token_ids)
                print(f"Subscribed to {len(token_ids)} position tokens")

        except Exception as e:
            print(f"Failed to subscribe positions: {e}")

    async def _check_all_positions(self, db: AsyncSession) -> None:
        """检查所有持仓的止损/止盈（用缓存价格）."""
        if not self._data_source:
            return

        try:
            result = await db.execute(
                select(Position).where(
                    Position.portfolio_id == self._portfolio_id,
                    Position.status == "open",
                )
            )
            positions = result.scalars().all()

            for position in positions:
                await self._check_position_with_datasource(db, position)

        except Exception as e:
            print(f"Failed to check positions: {e}")

    async def _check_position_with_datasource(
        self, db: AsyncSession, position: Position
    ) -> None:
        """使用 DataSource 获取实时价格并检查止损/止盈."""
        if not self._data_source:
            return

        token_id = position.token_id
        if not token_id:
            return

        try:
            # 使用 DataSource 获取市场数据（返回 WebSocket 缓存的价格）
            market_data = await self._data_source.get_market_data(token_id)
            if not market_data:
                return

            # 根据 side 获取当前价格
            current_price = Decimal(str(
                market_data.yes_price if position.side == "yes" else market_data.no_price
            ))
            position.current_price = current_price

            # 计算未实现盈亏
            position.calculate_unrealized_pnl(current_price)

        except Exception as e:
            # fallback: 使用缓存的 current_price
            current_price = position.current_price

        if not current_price:
            return

        # 检查止损/止盈
        await self._evaluate_exit_conditions(db, position, current_price)

    async def _evaluate_exit_conditions(
        self, db: AsyncSession, position: Position, current_price: Decimal
    ) -> None:
        """评估是否触发止损/止盈."""
        side = position.side

        # Polymarket 止盈止损逻辑：
        # Yes: 价格上涨盈利，下跌亏损
        # No: 价格下跌盈利，上涨亏损

        should_close = False
        close_reason = ""

        if side == "yes":
            # 检查止盈（价格上涨到目标）
            if position.take_profit_price and current_price >= position.take_profit_price:
                should_close = True
                close_reason = f"take_profit: price {current_price} >= target {position.take_profit_price}"
            # 检查止损（价格下跌到止损价）
            elif position.stop_loss_price and current_price <= position.stop_loss_price:
                should_close = True
                close_reason = f"stop_loss: price {current_price} <= stop {position.stop_loss_price}"
        else:  # side == "no"
            # 检查止盈（价格下跌到目标）
            if position.take_profit_price and current_price <= position.take_profit_price:
                should_close = True
                close_reason = f"take_profit: price {current_price} <= target {position.take_profit_price}"
            # 检查止损（价格上涨到止损价）
            elif position.stop_loss_price and current_price >= position.stop_loss_price:
                should_close = True
                close_reason = f"stop_loss: price {current_price} >= stop {position.stop_loss_price}"

        if should_close:
            await self._close_position(db, position, close_reason)

    async def _close_position(
        self,
        db: AsyncSession,
        position: Position,
        close_reason: str,
    ) -> None:
        """关闭持仓."""
        print(f"Closing position {position.id}: {close_reason}")

        try:
            # 获取当前价格（从缓存或重新获取）
            current_price = position.current_price

            if not self._data_source:
                print("No data source, cannot close position properly")
                position.status = "closed"
                position.closed_at = datetime.utcnow()
                await db.commit()
                return

            # 确定平仓方向
            close_side = "no" if position.side == "yes" else "yes"

            # 获取 token_id for 平仓方向
            token_id = position.token_id
            if not token_id:
                print(f"No token_id for position {position.id}")
                position.status = "closed"
                position.closed_at = datetime.utcnow()
                await db.commit()
                return

            # 获取市场价格
            try:
                market_data = await self._data_source.get_market_data(token_id)
                if market_data:
                    current_price = Decimal(str(
                        market_data.yes_price if close_side == "yes" else market_data.no_price
                    ))
            except Exception as e:
                print(f"Failed to get market price: {e}")

            # 计算盈亏
            size = position.size
            if position.side == "yes":
                pnl = (current_price - position.entry_price) * size
            else:
                pnl = (position.entry_price - current_price) * size

            # 更新持仓状态
            position.status = "closed"
            position.closed_at = datetime.utcnow()
            position.exit_price = current_price
            position.realized_pnl = pnl
            position.total_pnl = pnl + position.unrealized_pnl

            # 从缓存移除
            if position.token_id and position.token_id in self._position_cache:
                del self._position_cache[position.token_id]

            await db.commit()
            print(f"Position {position.id} closed: PnL = {pnl}")

        except Exception as e:
            print(f"Error closing position: {e}")
            await db.rollback()


# 全局实例
position_monitor = PositionMonitor()
