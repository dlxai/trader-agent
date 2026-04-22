"""Strategy runner service for scheduled execution."""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.wallet import Wallet
from src.models.signal_log import SignalLog
from src.models.order import Order
from src.models.provider import Provider
from src.services.data_source_manager import get_data_source_manager, DataSource, SignalFilter, TriggerChecker
from src.core.crypto import decrypt_private_key


class StrategyRunner:
    """Strategy execution runner."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._data_source_manager = get_data_source_manager()
        self.clob_client: Optional["ClobClient"] = None  # py-clob-client v2

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

        # Get or create shared data source
        data_source = await self._data_source_manager.get_or_create_source(
            portfolio_id=strategy.portfolio_id,
            source_type="polymarket"
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
                    await self._execute_strategy(db, strategy, data_source)
                    strategy.last_run_at = datetime.utcnow()
                    strategy.total_runs += 1
                    await db.commit()
                except Exception as e:
                    print(f"Strategy execution error: {e}")

                await asyncio.sleep(interval)
                await db.refresh(strategy)

    async def _execute_strategy(
        self, db: AsyncSession, strategy: Strategy, data_source: DataSource
    ) -> Optional[SignalLog]:
        """Execute strategy once."""

        # 1. 获取可用市场
        markets = await self._get_available_markets(strategy)

        if not markets:
            return None

        # 2. 初始化过滤器和触发器
        # 从 strategy.filters 获取过滤配置（JSON 字段）
        filter_config = {}
        if strategy.filters:
            filter_config = strategy.filters if isinstance(strategy.filters, dict) else {}
        elif strategy.position_monitor:
            # 兼容旧字段
            filter_config = {
                'min_confidence': 40,
                'min_price': 0.5,
                'max_price': 0.99,
                'max_hours_to_expiry': 6,
            }

        signal_filter = SignalFilter(filter_config)

        # 从 strategy.trigger 获取触发配置
        trigger_config = {}
        if strategy.trigger:
            trigger_config = strategy.trigger if isinstance(strategy.trigger, dict) else {}

        trigger_checker = TriggerChecker(trigger_config)

        # 3. 检查冷却时间
        if not trigger_checker.check_cooldown():
            return None

        # 4. 获取数据源并过滤市场 + 检查触发条件
        triggered_markets = []
        for market in markets:
            token_id = market.get("id") or market.get("token_id")
            if not token_id:
                continue

            # 获取实时价格数据
            market_data = await data_source.get_market_data(token_id)
            if not market_data:
                continue

            # 应用 SignalFilter 过滤
            if not signal_filter.filter_market(market_data):
                continue

            # 检查关键词过滤
            market_name = market.get("question", market.get("symbol", ""))
            if not signal_filter.filter_by_keywords(market_name):
                continue

            # 检查触发条件（价格波动 + 净流入）
            # 先检查价格波动触发
            old_price = market.get("price", 0.5)
            new_price = market_data.yes_price

            price_triggered = trigger_checker.check_price_trigger(old_price, new_price)

            # 检查 Activity 净流入触发
            activity_data = await data_source.get_activity(token_id)
            netflow = activity_data.netflow if activity_data else 0
            activity_triggered = trigger_checker.check_activity_trigger(netflow, new_price)

            if price_triggered or activity_triggered:
                # 标记触发，给 AI 更多参考
                market["_triggered"] = True
                market["_price_change"] = abs(new_price - old_price) / old_price * 100 if old_price > 0 else 0
                market["_netflow"] = netflow

            triggered_markets.append(market)

        if not triggered_markets:
            return None

        # 5. 调用 AI 分析
        ai_result = await self._call_ai_analysis(strategy, triggered_markets)

        if not ai_result:
            return None

        # 6. AI 置信度过滤
        confidence = ai_result.get("confidence", 0)
        min_confidence = signal_filter.min_confidence / 100  # 转换为 0-1
        if confidence < min_confidence:
            return None

        # 7. 标记触发成功
        trigger_checker.update_trigger_time()

        # 8. 计算下单金额
        order_size = self._calculate_order_size(
            strategy, confidence
        )

        # 9. 创建 SignalLog
        # 从 triggered_markets 列表中获取对应的市场
        market_id = ai_result.get("market_id", "")
        symbol = ai_result.get("symbol", "")

        # 尝试从 triggered_markets 中找到对应的市场
        selected_market = None
        for m in triggered_markets:
            if m.get("id") == market_id or m.get("symbol") == symbol:
                selected_market = m
                break

        if not selected_market and triggered_markets:
            selected_market = triggered_markets[0]

        if selected_market:
            market_id = market_id or selected_market.get("id", "")
            symbol = symbol or selected_market.get("symbol", "")

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
        """从 Gamma API 获取可用市场"""
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
            return [m for m in markets if m.get("active") and m.get("volume", 0) > 1000]
        except Exception as e:
            print(f"Failed to fetch markets from Gamma API: {e}")
            return []

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
        """使用 py-clob-client v2 执行订单"""
        if not self.clob_client:
            print("ClobClient not initialized")
            return

        market_id = signal_log.market_id
        if not market_id:
            print("No market_id in signal")
            return

        try:
            # 1. 从 Gamma API 获取市场详情（token_id）
            token_id = await self._get_token_id(market_id, signal_log.side)
            if not token_id:
                print(f"Token not found for side: {signal_log.side}")
                return

            # 2. 执行市价单（py-clob-client 是同步的，用 to_thread 跑）
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

            print(f"Order placed: {result}")

            # 3. 创建 Order 记录
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
            )
            db.add(order)
            await db.commit()

        except Exception as e:
            print(f"Order execution failed: {e}")
            import traceback
            traceback.print_exc()
            signal_log.status = "failed"
            await db.commit()

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

            # 先查 tokens 数组
            for token in market.get("tokens", []):
                if token.get("outcome", "").lower() == side.lower():
                    return token.get("token_id")

            # 备用：clob_token_ids
            clob_ids = market.get("clob_token_ids", {})
            if isinstance(clob_ids, dict):
                return clob_ids.get(side.lower())

        except Exception as e:
            print(f"Failed to get token_id from Gamma API: {e}")

        return None


# 全局实例
strategy_runner = StrategyRunner()