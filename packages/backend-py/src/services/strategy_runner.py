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
from src.models.provider import Provider
from src.services.data_source_manager import get_data_source_manager, DataSource


class StrategyRunner:
    """Strategy execution runner."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._data_source_manager = get_data_source_manager()
        self.sdk: Optional[PolymarketSDK] = None

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

        # Get or create shared data source
        data_source = await self._data_source_manager.get_or_create_source(
            portfolio_id=strategy.portfolio_id,
            source_type="polymarket",
            proxy_url="http://127.0.0.1:7890"
        )

        task = asyncio.create_task(self._run_strategy_loop(strategy_id, data_source))
        self._tasks[strategy_id] = task

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]

        # Optionally cleanup data source if no strategies are running for this portfolio
        # Note: DataSourceManager handles lifecycle, so we don't close here
        # to allow sharing across multiple strategies

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
        import httpx
        import json
        from datetime import datetime

        # 1. 获取 Provider 配置
        provider = None
        if strategy.provider_id:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Provider).where(Provider.id == strategy.provider_id)
                )
                provider = result.scalar_one_or_none()

        if not provider or not provider.api_key:
            print(f"No provider or API key found for strategy {strategy.id}")
            # 返回一个模拟结果用于测试
            return self._generate_mock_ai_result(markets)

        # 2. 构建 Prompt
        system_prompt = strategy.system_prompt or self._get_default_system_prompt()
        user_prompt = self._build_user_prompt(strategy, markets)

        # 3. 准备 API 请求
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

        # 4. 调用 AI API
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

            # 5. 解析响应
            content = result["choices"][0]["message"]["content"]
            ai_result = json.loads(content)

            # 添加元数据
            ai_result["model"] = model
            ai_result["duration_ms"] = duration_ms
            ai_result["tokens_used"] = result.get("usage", {}).get("total_tokens", 0)

            # 添加输入摘要
            ai_result["input_summary"] = {
                "markets_count": len(markets),
                "data_sources": strategy.data_sources or {},
                "market_filter_days": strategy.market_filter_days,
            }

            # 如果 AI 没有指定市场，选择第一个
            if not ai_result.get("market_id") and markets:
                ai_result["market_id"] = markets[0].get("id", "")
                ai_result["symbol"] = markets[0].get("symbol", "")

            print(f"AI analysis completed: {ai_result.get('action')} {ai_result.get('side')} @ {ai_result.get('confidence')}")
            return ai_result

        except Exception as e:
            print(f"AI API call failed: {e}")
            # 返回模拟结果
            return self._generate_mock_ai_result(markets)

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for trading."""
        return """You are a Polymarket trading expert. Analyze markets and provide trading signals.

Your task is to:
1. Analyze market data including prices, volume, and recent activity
2. Identify trading opportunities based on the data
3. Provide clear buy/sell/hold signals with confidence levels
4. Include stop-loss and take-profit recommendations

Response format (JSON):
{
  "action": "buy" | "sell" | "hold",
  "side": "yes" | "no",
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation",
  "thinking": "your analysis process",
  "stop_loss": recommended stop loss price,
  "take_profit": recommended take profit price,
  "risk_reward": risk/reward ratio,
  "market_id": "the selected market ID",
  "symbol": "market symbol"
}

Consider:
- Market liquidity and volume
- Recent price movements
- Time until market expiration
- Risk management principles"""

    def _get_default_api_base(self, provider_type: str) -> str:
        """Get default API base URL for provider."""
        bases = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "azure": "https://{resource}.openai.azure.com/openai/deployments/{deployment}",
        }
        return bases.get(provider_type, "https://api.openai.com/v1")

    def _build_user_prompt(self, strategy: Strategy, markets: list[dict]) -> str:
        """Build user prompt with market data."""
        # 格式化市场数据
        markets_info = []
        for i, m in enumerate(markets[:10]):  # 限制前10个市场
            markets_info.append(f"""
Market {i+1}:
- ID: {m.get('id', 'N/A')}
- Symbol: {m.get('symbol', 'N/A')}
- Question: {m.get('question', 'N/A')}
- Current Price: {m.get('price', 'N/A')}
- Volume 24h: ${m.get('volume', 0):,.0f}
- Liquidity: ${m.get('liquidity', 0):,.0f}
- End Date: {m.get('endDate', 'N/A')}
- Active: {m.get('active', False)}
""")

        prompt = f"""Analyze the following Polymarket markets and provide a trading signal.

Strategy: {strategy.name}
Description: {strategy.description or 'N/A'}

Available Markets (ending within {strategy.market_filter_days or 24} hours):
{''.join(markets_info)}

{system_prompt if (system_prompt := strategy.custom_prompt) else ''}

Provide your analysis and trading decision in JSON format."""

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

        # 随机选择一个市场
        import random
        market = random.choice(markets)
        price = market.get("price", 0.5)

        # 随机决策（测试用）
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