"""Position monitor for stop-loss and take-profit."""

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.position import Position
from src.models.order import Order
from src.models.wallet import Wallet
from src.core.crypto import decrypt_private_key


class PositionMonitor:
    """Monitor positions for stop-loss and take-profit triggers."""

    def __init__(self):
        self._running = False
        self._check_interval = 60  # Check every 60 seconds
        self.clob_client: Optional["ClobClient"] = None

    async def start(self) -> None:
        """Start the position monitor."""
        self._running = True

        # 获取活跃的 wallet 以获取 proxy_wallet_address
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Wallet).where(Wallet.is_active == True).limit(1)
            )
            wallet = result.scalar_one_or_none()

            private_key_raw = wallet.private_key_encrypted if wallet else None
            private_key = decrypt_private_key(private_key_raw) if private_key_raw else None
            proxy_wallet_address = wallet.proxy_wallet_address if wallet else None

        # 初始化 ClobClient v2
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

            self.clob_client = ClobClient(**kwargs)
            api_creds = self.clob_client.create_or_derive_api_creds()
            self.clob_client.set_api_creds(api_creds)
        except Exception as e:
            print(f"Failed to initialize ClobClient: {e}")
            raise

        asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the position monitor."""
        self._running = False
        self.clob_client = None

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    await self._check_positions(db)
            except Exception as e:
                print(f"Position monitor error: {e}")

            await asyncio.sleep(self._check_interval)

    async def _check_positions(self, db: AsyncSession) -> None:
        """Check all open positions for stop-loss/take-profit."""
        result = await db.execute(
            select(Position).where(Position.status == "open")
        )
        positions = result.scalars().all()

        for position in positions:
            await self._check_position(db, position)

    async def _check_position(
        self, db: AsyncSession, position: Position
    ) -> None:
        """Check a single position."""

        current_price = position.current_price

        if self.clob_client and position.condition_id:
            try:
                # 先从 Gamma API 获取 token_id
                token_id = await self._get_token_id(position.condition_id, position.side)
                if token_id:
                    from py_clob_client.order_builder.constants import BUY, SELL
                    # 获取当前价格（py-clob-client 是同步的）
                    side = BUY if position.side == "yes" else SELL
                    price_data = await asyncio.to_thread(
                        self.clob_client.get_price, token_id, side
                    )
                    price_val = price_data if isinstance(price_data, (int, float)) else price_data.get("price", 0)
                    current_price = Decimal(str(price_val))
                    position.current_price = current_price
            except Exception as e:
                print(f"Failed to get price: {e}")

        if not current_price:
            return

        # Polymarket 止盈止损逻辑：
        # 买入 Yes: 概率上涨时盈利，下跌时亏损
        # 买入 No: 概率下跌时盈利，上涨时亏损

        if position.side == "yes":
            # 买入 Yes - 检查止盈（概率上涨）
            if (
                position.take_profit_price
                and current_price >= position.take_profit_price
            ):
                await self._close_position(db, position, "take_profit")

            # 检查止损（概率下跌）
            elif (
                position.stop_loss_price
                and current_price <= position.stop_loss_price
            ):
                await self._close_position(db, position, "stop_loss")

        else:  # side == "no"
            # 买入 No - 检查止盈（概率下跌）
            if (
                position.take_profit_price
                and current_price <= position.take_profit_price
            ):
                await self._close_position(db, position, "take_profit")

            # 检查止损（概率上涨）
            elif (
                position.stop_loss_price
                and current_price >= position.stop_loss_price
            ):
                await self._close_position(db, position, "stop_loss")

    async def _get_token_id(self, condition_id: str, side: str) -> Optional[str]:
        """从 Gamma API 获取指定 outcome 的 token_id."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://gamma-api.polymarket.com/markets/{condition_id}",
                    timeout=10,
                )
                resp.raise_for_status()
                market = resp.json()

            for token in market.get("tokens", []):
                if token.get("outcome", "").lower() == side.lower():
                    return token.get("token_id")

            clob_ids = market.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                return clob_ids.get(side.lower())
        except Exception as e:
            print(f"Failed to get token_id from Gamma API: {e}")
        return None

    async def _close_position(
        self,
        db: AsyncSession,
        position: Position,
        close_reason: str,
    ) -> None:
        """Close a position due to stop-loss or take-profit."""
        from src.models.order import Order
        from src.models.wallet import Wallet
        from src.models.signal_log import SignalLog
        from uuid import UUID

        print(f"Closing position {position.id} due to {close_reason}")

        if not self.clob_client:
            print("ClobClient not initialized, cannot close position")
            return

        try:
            # 获取当前价格
            current_price = position.current_price
            if position.condition_id:
                token_id = await self._get_token_id(position.condition_id, position.side)
                if token_id:
                    from py_clob_client.order_builder.constants import BUY, SELL
                    side = BUY if position.side == "yes" else SELL
                    price_data = await asyncio.to_thread(
                        self.clob_client.get_price, token_id, side
                    )
                    price_val = price_data if isinstance(price_data, (int, float)) else price_data.get("price", 0)
                    current_price = Decimal(str(price_val))

            if not current_price:
                print("Cannot get current price, skipping close")
                return

            # 计算平仓数量 (与开仓相同)
            size = position.size
            if not size or size <= 0:
                print("Invalid position size, skipping close")
                return

            # 确定平仓方向 (与开仓相反)
            close_side = "no" if position.side == "yes" else "yes"

            # 获取 token_id
            token_id = None
            if position.market_id:
                token_id = await self._get_token_id(position.market_id, close_side)

            if not token_id:
                print(f"Cannot find token_id for market {position.market_id}")
                # 仍然标记为关闭
                position.status = "closed"
                position.closed_at = datetime.utcnow()
                position.close_reason = close_reason
                await db.commit()
                return

            # 创建平仓订单
            order = Order(
                id=UUID(),
                user_id=position.user_id,
                portfolio_id=position.portfolio_id,
                strategy_id=position.strategy_id,
                position_id=position.id,
                order_type="sell" if position.side == "yes" else "buy",
                side=close_side,
                token_id=token_id,
                market_id=position.market_id,
                size=size,
                price=current_price,
                status="pending",
                filled_size=Decimal("0"),
                filled_price=Decimal("0"),
                fees=Decimal("0"),
            )
            db.add(order)

            # 更新 Position 状态
            position.status = "closed"
            position.closed_at = datetime.utcnow()
            position.close_reason = close_reason
            position.close_price = current_price

            # 计算盈亏
            if position.side == "yes":
                # 买入 Yes: 盈利 = (平仓价 - 开仓价) * 数量
                pnl = (current_price - position.entry_price) * size
            else:
                # 买入 No: 盈利 = (开仓价 - 平仓价) * 数量
                pnl = (position.entry_price - current_price) * size

            position.pnl = pnl

            # 更新相关的 SignalLog
            if position.signal_id:
                result = await db.execute(
                    select(SignalLog).where(SignalLog.signal_id == position.signal_id)
                )
                signal = result.scalar_one_or_none()
                if signal:
                    signal.status = "executed"
                    signal.executed_at = datetime.utcnow()
                    signal.execution_price = current_price
                    signal.execution_size = size
                    signal.was_profitable = pnl > 0
                    signal.actual_outcome = close_reason

            await db.commit()
            print(f"Position {position.id} closed: {close_reason}, PnL: {pnl}")

        except Exception as e:
            print(f"Error closing position: {e}")
            await db.rollback()


# 全局实例
position_monitor = PositionMonitor()
