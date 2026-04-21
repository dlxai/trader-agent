"""Position monitor for stop-loss and take-profit."""

import asyncio
import sys
from decimal import Decimal
from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/d/wework/polymarket-agent")
from polymarket_sdk.sdk import PolymarketSDK

from src.database import AsyncSessionLocal
from src.models.position import Position
from src.models.order import Order
from src.models.wallet import Wallet


class PositionMonitor:
    """Monitor positions for stop-loss and take-profit triggers."""

    def __init__(self):
        self._running = False
        self._check_interval = 60  # Check every 60 seconds
        self.sdk: Optional[PolymarketSDK] = None

    async def start(self) -> None:
        """Start the position monitor."""
        self._running = True

        # 获取活跃的 wallet 以获取 proxy_wallet_address
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Wallet).where(Wallet.is_active == True).limit(1)
            )
            wallet = result.scalar_one_or_none()

            private_key = wallet.private_key_encrypted if wallet else None
            proxy_wallet_address = wallet.proxy_wallet_address if wallet else None

        # 初始化 SDK
        try:
            self.sdk = await PolymarketSDK.create(
                private_key=private_key,
                proxy_wallet_address=proxy_wallet_address
            )
        except Exception as e:
            print(f"Failed to initialize SDK: {e}")
            raise

        asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the position monitor."""
        self._running = False

        if self.sdk:
            try:
                await self.sdk.close()
            except Exception as e:
                print(f"Failed to close Polymarket SDK: {e}")
            self.sdk = None

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

        # 使用 SDK 获取实时价格
        current_price = position.current_price

        if self.sdk and position.condition_id:
            try:
                ticker = await self.sdk.clob_api.get_ticker(position.condition_id)
                current_price = Decimal(str(ticker.get("price", 0)))
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

    async def _close_position(
        self,
        db: AsyncSession,
        position: Position,
        close_reason: str,
    ) -> None:
        """Close a position due to stop-loss or take-profit."""
        # TODO: 实现平仓订单
        # 1. 获取当前价格
        # 2. 创建卖出订单（与开仓方向相反）
        # 3. 调用 Polymarket API
        # 4. 更新 Position 状态

        print(f"Closing position {position.id} due to {close_reason}")

        # 标记为关闭（实际实现需要完善）
        # position.status = "closed"
        # await db.commit()


# 全局实例
position_monitor = PositionMonitor()
