"""Strategy runner service for scheduled execution."""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/d/wework/polymarket-agent")
from polymarket_sdk.sdk import PolymarketSDK
from polymarket_sdk.services.trading_service import Side

from src.database import AsyncSessionLocal
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.wallet import Wallet
from src.models.signal_log import SignalLog
from src.models.order import Order
from src.models.position import Position
from src.models.provider import Provider


class StrategyRunner:
    """Strategy execution runner."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self.sdk: Optional[PolymarketSDK] = None

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        if strategy_id in self._tasks:
            return  # Already running

        # 初始化 SDK
        try:
            self.sdk = await PolymarketSDK.create()
        except Exception as e:
            print(f"Failed to initialize Polymarket SDK: {e}")
            raise

        task = asyncio.create_task(self._run_strategy_loop(strategy_id))
        self._tasks[strategy_id] = task

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]

        if self.sdk:
            try:
                await self.sdk.close()
            except Exception as e:
                print(f"Failed to close Polymarket SDK: {e}")
            self.sdk = None

    async def _run_strategy_loop(self, strategy_id: UUID) -> None:
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
                    await self._execute_strategy(db, strategy)
                    strategy.last_run_at = datetime.utcnow()
                    strategy.total_runs += 1
                    await db.commit()
                except Exception as e:
                    print(f"Strategy execution error: {e}")

                await asyncio.sleep(interval)
                await db.refresh(strategy)

    async def _execute_strategy(
        self, db: AsyncSession, strategy: Strategy
    ) -> Optional[SignalLog]:
        """Execute strategy once."""

        # 1. 获取可用市场（根据过滤条件）
        markets = await self._get_available_markets(strategy)

        if not markets:
            return None

        # 2. 调用 AI 分析
        ai_result = await self._call_ai_analysis(strategy, markets)

        if not ai_result:
            return None

        # 3. 计算下单金额
        order_size = self._calculate_order_size(
            strategy, ai_result.get("confidence", 0.5)
        )

        # 4. 创建 SignalLog
        # 从 markets 列表中获取第一个市场（简化示例，实际应该根据 ai_result 选择对应的市场）
        market = markets[0] if markets else {}
        market_id = market.get("id", "")
        symbol = market.get("symbol", "")

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

        # 5. 如果是买入/卖出信号，执行订单
        if ai_result.get("action") in ["buy", "sell"]:
            await self._execute_order(db, strategy, signal_log)

        return signal_log

    async def _get_available_markets(self, strategy: Strategy) -> list[dict]:
        """使用 SDK v2 获取可用市场"""
        # 计算截止时间
        hours = strategy.market_filter_days * 24 if strategy.market_filter_days else 24

        # 获取即将到期的市场
        markets = await self.sdk.gamma_api.get_markets_ending_within_hours(hours)

        # 过滤活跃市场
        return [m for m in markets if m.get("active") and m.get("volume", 0) > 1000]

    async def _call_ai_analysis(
        self, strategy: Strategy, markets: list[dict]
    ) -> Optional[dict]:
        """Call AI to analyze markets."""
        # TODO: 实现 AI 调用
        # 1. 构建 Prompt（使用 strategy.system_prompt, strategy.custom_prompt）
        # 2. 调用 Provider（获取 API key）
        # 3. 解析响应
        return None

    def _calculate_order_size(
        self, strategy: Strategy, confidence: float
    ) -> Decimal:
        """Calculate order size based on confidence."""
        min_size = float(strategy.min_order_size)
        max_size = float(strategy.max_order_size)

        # 线性插值
        order_size = min_size + (max_size - min_size) * confidence

        # 限制范围
        return Decimal(str(max(min_size, min(max_size, order_size))))

    async def _execute_order(
        self,
        db: AsyncSession,
        strategy: Strategy,
        signal_log: SignalLog,
    ) -> None:
        """使用 SDK v2 执行订单"""
        if not self.sdk:
            print("SDK not initialized")
            return

        try:
            # 1. 从 signal_log 获取 market 信息
            # signal_log 应该有 market_id 或 condition_id
            market_id = signal_log.market_id

            if not market_id:
                print("No market_id in signal")
                return

            # 2. 获取市场详情，包含 token_id
            market = await self.sdk.gamma_api.get_market(market_id)

            if not market:
                print(f"Market not found: {market_id}")
                return

            # 3. 根据 side (yes/no) 获取对应的 token_id
            side = "yes" if signal_log.side == "yes" else "no"

            # 从市场数据中获取 token_id
            # 市场数据通常包含 tokens 或 clob_token_ids
            tokens = market.get("tokens", [])

            token_id = None
            for token in tokens:
                if token.get("outcome") == side:
                    token_id = token.get("token_id")
                    break

            if not token_id:
                # 备用：从 clob_token_ids 获取
                clob_token_ids = market.get("clob_token_ids", {})
                token_id = clob_token_ids.get(side)

            if not token_id:
                print(f"Token not found for side: {side}")
                return

            # 4. 执行市价单
            order_side = Side.YES if signal_log.side == "yes" else Side.NO

            result = await self.sdk.trading_service.create_market_order(
                token_id=token_id,
                side=order_side,
                amount=float(signal_log.size),
                order_type="GTC"
            )

            print(f"Order placed: {result}")

            # 5. 创建 Order 记录
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
                filled_size=Decimal(str(result.get("size", signal_log.size))),
                status="filled",
                # 其他必要字段...
            )
            db.add(order)
            await db.commit()

        except Exception as e:
            print(f"Order execution failed: {e}")
            import traceback
            traceback.print_exc()
            signal_log.status = "failed"
            await db.commit()


# 全局实例
strategy_runner = StrategyRunner()