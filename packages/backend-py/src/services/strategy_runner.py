"""Strategy runner service for scheduled execution."""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        if strategy_id in self._tasks:
            return  # Already running

        task = asyncio.create_task(self._run_strategy_loop(strategy_id))
        self._tasks[strategy_id] = task

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]

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
        )

        db.add(signal_log)
        await db.commit()

        # 5. 如果是买入/卖出信号，执行订单
        if ai_result.get("action") in ["buy", "sell"]:
            await self._execute_order(db, strategy, signal_log)

        return signal_log

    async def _get_available_markets(self, strategy: Strategy) -> list[dict]:
        """Get available markets based on filter."""
        # TODO: 实现 Polymarket 市场查询
        # 根据 strategy.market_filter_days 过滤
        # 返回示例: [{"id": "xxx", "name": "Trump 2024", "end_date": "..."}]
        return []

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
        """Execute order based on signal."""
        # TODO: 实现订单执行
        # 1. 获取 Wallet
        # 2. 创建 Order
        # 3. 调用 Polymarket API
        # 4. 创建 Position


# 全局实例
strategy_runner = StrategyRunner()