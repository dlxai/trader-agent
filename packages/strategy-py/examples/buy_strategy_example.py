"""
买入策略使用示例

演示如何使用 BuyStrategy 进行完整的买入决策流程
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 导入策略组件
from strategy import (
    # 主策略
    BuyStrategy,
    BuyStrategyConfig,
    PortfolioState,

    # 信号生成
    Signal,
    SignalType,
    SignalStrength,
    TechnicalSignalGenerator,
    FundamentalSignalGenerator,
    CapitalFlowSignalGenerator,
    FundamentalConfig,

    # 入场条件
    EntryConditionValidator,
    EntryConditionConfig,
    EntryValidationResult,

    # 仓位大小
    PositionSizer,
    PositionSizerConfig,
    PositionSizingMethod,
    PortfolioState as PositionPortfolio,

    # 执行策略
    ExecutionStrategyType,
    Order,
    OrderType,
    OrderStatus,
)


# ==================== 模拟数据源 ====================

class MockPriceDataSource:
    """模拟价格数据源"""

    def __init__(self, base_price: float = 0.5):
        self.base_price = base_price
        self.price_history: Dict[str, List[Dict[str, Any]]] = {}

    def get_price_history(
        self,
        market_id: str,
        timeframe: str = "1h",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取价格历史"""
        if market_id not in self.price_history:
            # 生成模拟数据
            import random
            prices = []
            base = self.base_price
            for i in range(limit):
                # 随机游走
                change = random.gauss(0, 0.02)
                base *= (1 + change)
                base = max(0.01, min(0.99, base))  # 限制在 0.01-0.99

                prices.append({
                    "timestamp": datetime.now() - timedelta(hours=limit-i),
                    "open": base * (1 + random.gauss(0, 0.005)),
                    "high": base * (1 + abs(random.gauss(0, 0.01))),
                    "low": base * (1 - abs(random.gauss(0, 0.01))),
                    "close": base,
                    "volume": random.uniform(1000, 10000),
                })
            self.price_history[market_id] = prices

        return self.price_history[market_id][-limit:]

    def get_current_price(self, market_id: str) -> Optional[float]:
        """获取当前价格"""
        history = self.get_price_history(market_id, limit=1)
        if history:
            return history[-1].get("close")
        return self.base_price


class MockMarketDataSource:
    """模拟市场数据源"""

    def __init__(self):
        self.liquidity_cache: Dict[str, float] = {}

    def get_order_book(self, market_id: str) -> Dict[str, Any]:
        """获取订单簿"""
        import random
        return {
            "bids": [
                {"price": 0.48, "size": random.uniform(100, 1000)},
                {"price": 0.47, "size": random.uniform(200, 2000)},
            ],
            "asks": [
                {"price": 0.52, "size": random.uniform(100, 1000)},
                {"price": 0.53, "size": random.uniform(200, 2000)},
            ],
        }

    def get_recent_trades(self, market_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近交易"""
        import random
        trades = []
        for i in range(limit):
            side = "buy" if random.random() > 0.5 else "sell"
            price = random.uniform(0.45, 0.55)
            size = random.uniform(10, 1000)
            trades.append({
                "timestamp": datetime.now() - timedelta(minutes=i),
                "side": side,
                "price": price,
                "size": size,
            })
        return trades

    def get_liquidity(self, market_id: str) -> float:
        """获取流动性"""
        if market_id not in self.liquidity_cache:
            import random
            self.liquidity_cache[market_id] = random.uniform(5000, 50000)
        return self.liquidity_cache[market_id]


class MockOddsDataSource:
    """模拟赔率数据源"""

    def get_market_odds(self, market_id: str) -> Dict[str, Any]:
        """获取市场赔率"""
        import random
        implied_prob = random.uniform(0.4, 0.6)
        estimated_prob = implied_prob + random.gauss(0, 0.05)

        return {
            "market_id": market_id,
            "implied_probability": implied_prob,
            "estimated_probability": estimated_prob,
            "best_odds": 1 / implied_prob if implied_prob > 0 else 2.0,
            "true_odds": 1 / estimated_prob if estimated_prob > 0 else 2.0,
        }

    def get_implied_probability(self, market_id: str, outcome: str) -> Optional[float]:
        """获取隐含概率"""
        odds = self.get_market_odds(market_id)
        return odds.get("implied_probability")


class MockEventDataSource:
    """模拟事件数据源"""

    def get_event_calendar(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取事件日历"""
        import random
        events = []
        current = start_date
        while current < end_date:
            if random.random() > 0.7:  # 30% 概率有事件
                events.append({
                    "event_id": f"evt_{int(current.timestamp())}",
                    "datetime": current,
                    "type": random.choice(["earnings", "economic", "political", "sports"]),
                    "importance": random.choice(["low", "medium", "high"]),
                    "description": f"Mock event at {current}",
                })
            current += timedelta(hours=random.randint(1, 12))
        return events

    def get_market_events(self, market_id: str) -> List[Dict[str, Any]]:
        """获取市场相关事件"""
        now = datetime.now()
        return self.get_event_calendar(now - timedelta(days=1), now + timedelta(days=7))


class MockMarketInfoSource:
    """模拟市场信息源"""

    def get_market_info(self, market_id: str) -> Dict[str, Any]:
        """获取市场信息"""
        return {
            "market_id": market_id,
            "status": "active",
            "category": "crypto",
            "created_at": datetime.now() - timedelta(days=30),
        }

    def get_market_expiry(self, market_id: str) -> Optional[datetime]:
        """获取市场到期时间"""
        # 模拟永不到期或还有很长时间的合约
        return datetime.now() + timedelta(days=365)

    def get_market_category(self, market_id: str) -> Optional[str]:
        """获取市场分类"""
        return "crypto"


class MockLiquiditySource:
    """模拟流动性数据源"""

    def get_available_liquidity(self, market_id: str) -> float:
        """获取可用流动性"""
        import random
        return random.uniform(5000, 50000)

    def get_order_book_depth(self, market_id: str) -> Dict[str, float]:
        """获取订单簿深度"""
        return {
            "bid": 15000,
            "ask": 15000,
        }


class MockVolatilitySource:
    """模拟波动率数据源"""

    def get_volatility(self, market_id: str, period: str = "24h") -> float:
        """获取波动率"""
        import random
        return random.uniform(0.01, 0.20)  # 1% 到 20%

    def get_price_range(self, market_id: str, period: str = "24h") -> Tuple[float, float]:
        """获取价格范围"""
        import random
        low = random.uniform(0.4, 0.5)
        high = low * random.uniform(1.02, 1.10)
        return (low, high)


# ==================== 主函数 ====================

async def main():
    """主函数 - 演示使用流程"""

    print("=" * 60)
    print("买入策略演示")
    print("=" * 60)

    # 创建模拟数据源
    print("\n1. 初始化数据源...")
    price_source = MockPriceDataSource(base_price=0.5)
    market_data_source = MockMarketDataSource()
    odds_source = MockOddsDataSource()
    event_source = MockEventDataSource()
    market_info_source = MockMarketInfoSource()
    liquidity_source = MockLiquiditySource()
    volatility_source = MockVolatilitySource()

    # 创建策略配置
    print("\n2. 配置策略...")
    config = BuyStrategyConfig(
        min_signal_strength=SignalStrength.WEAK,
        min_signal_confidence=0.5,
        entry_config=EntryConditionConfig(
            min_liquidity=500,
            allow_death_zone=False,
        ),
        position_config=PositionSizerConfig(
            default_method=PositionSizingMethod.FIXED_RISK,
            fixed_risk_percentage=0.02,
        ),
        default_execution_strategy=ExecutionStrategyType.IMMEDIATE,
    )

    # 创建主策略
    print("\n3. 初始化策略...")
    strategy = BuyStrategy(
        config=config,
        price_source=price_source,
        market_data_source=market_data_source,
        odds_source=odds_source,
        event_source=event_source,
        market_info_source=market_info_source,
        liquidity_source=liquidity_source,
        volatility_source=volatility_source,
    )

    # 设置投资组合
    portfolio = PortfolioState(
        total_capital=10000.0,
        available_capital=10000.0,
        total_risk_exposure=0.0,
    )
    strategy.set_portfolio(portfolio)

    # 激活策略
    strategy.activate()

    # 注册事件回调
    def on_signal(data):
        print(f"  [事件] 信号生成: {len(data)} 个信号")

    def on_entry_validated(data):
        print(f"  [事件] 入场验证: {'通过' if data.can_enter else '失败'}")

    def on_position_sized(data):
        print(f"  [事件] 仓位计算: ${data.final_size:.2f}")

    def on_order_executed(data):
        print(f"  [事件] 订单执行: {data.trade_id}")

    strategy.register_callback("signal_generated", on_signal)
    strategy.register_callback("entry_validated", on_entry_validated)
    strategy.register_callback("position_sized", on_position_sized)
    strategy.register_callback("order_executed", on_order_executed)

    # 模拟市场评估
    print("\n4. 评估市场...")
    market_id = "mock-market-001"

    # 获取当前价格
    current_price = price_source.get_current_price(market_id)
    print(f"  当前价格: ${current_price:.4f}")

    # 评估市场
    eval_result = await strategy.evaluate_market(market_id, current_price)

    print(f"\n  评估结果:")
    print(f"  - 可入场: {eval_result['can_enter']}")
    print(f"  - 信号数量: {len(eval_result['signals'])}")

    if eval_result['signals']:
        print(f"\n  信号详情:")
        for i, sig in enumerate(eval_result['signals'][:3], 1):
            print(f"  {i}. {sig['type']}: {sig['strength']} (置信度: {sig['confidence']:.2f})")

    if eval_result['entry_validation']:
        validation = eval_result['entry_validation']
        print(f"\n  入场验证:")
        print(f"  - 结果: {'通过' if validation['can_enter'] else '失败'}")
        print(f"  - 通过率: {validation['pass_rate']:.1%}")
        print(f"  - 检查项: {len(validation['checks'])}")

    if eval_result['position_sizing']:
        sizing = eval_result['position_sizing']
        print(f"\n  仓位大小:")
        print(f"  - 建议仓位: ${sizing['final_size']:.2f}")
        print(f"  - 风险金额: ${sizing['final_risk_amount']:.2f}")
        print(f"  - 计算方法: {sizing['method']}")

    # 尝试执行买入（如果评估通过）
    if eval_result['can_enter'] and eval_result['position_sizing']:
        print("\n5. 执行买入...")

        position_size = eval_result['position_sizing']['final_size']
        entry_price = eval_result['position_sizing'].get('entry_price', current_price)

        success, trade = await strategy.enter_position(
            market_id=market_id,
            size=position_size,
            price=entry_price,
            execution_strategy=ExecutionStrategyType.IMMEDIATE,
        )

        if success and trade:
            print(f"  买入成功!")
            print(f"  - 交易ID: {trade.trade_id}")
            print(f"  - 数量: {trade.size:.4f}")
            print(f"  - 入场价格: ${trade.entry_price:.4f}")
            print(f"  - 总价值: ${trade.value:.2f}")
        else:
            print(f"  买入失败")

    # 显示策略统计
    print("\n6. 策略统计...")
    stats = strategy.get_stats()
    print(f"  - 策略激活: {stats['is_active']}")
    print(f"  - 今日交易: {stats['daily_trade_count']}")
    print(f"  - 总交易数: {stats['total_trades']}")
    print(f"  - 开仓交易: {stats['open_trades']}")
    print(f"  - 总资金: ${stats['portfolio']['total_capital']:,.2f}")
    print(f"  - 可用资金: ${stats['portfolio']['available_capital']:,.2f}")
    print(f"  - 资金利用率: {stats['portfolio']['utilization_rate']:.1%}")

    # 停用策略
    strategy.deactivate()
    print("\n策略演示完成!")


# ==================== 高级示例 ====================

async def advanced_example():
    """高级使用示例"""

    print("\n" + "=" * 60)
    print("高级策略配置示例")
    print("=" * 60)

    # 创建高级配置
    config = BuyStrategyConfig(
        # 信号配置
        min_signal_strength=SignalStrength.MODERATE,
        min_signal_confidence=0.65,
        max_signals_per_market=3,

        # 入场条件配置
        entry_config=EntryConditionConfig(
            price_min=0.10,
            price_max=0.90,
            death_zone_min=0.55,
            death_zone_max=0.80,
            allow_death_zone=False,
            min_liquidity=2000,
            min_order_book_depth=1000,
            min_time_to_expiry=timedelta(hours=12),
            avoid_expiry_within=timedelta(hours=3),
            max_volatility=0.30,
            min_volatility=0.005,
        ),

        # 仓位配置
        position_config=PositionSizerConfig(
            default_method=PositionSizingMethod.CONFIDENCE_WEIGHTED,
            kelly_fraction=0.20,
            fixed_risk_percentage=0.015,
            base_position_pct=0.08,
            min_position_pct=0.01,
            max_position_pct=0.20,
            max_single_position_pct=0.25,
            max_total_exposure_pct=0.70,
            min_trade_size=50.0,
            enable_multiple_methods=True,
            combine_method="weighted_average",
        ),

        # 执行配置
        default_execution_strategy=ExecutionStrategyType.DCA,
        dca_batches=4,
        dca_interval_seconds=30,
        twap_slices=8,
        twap_duration_seconds=240,

        # 风险控制
        max_daily_trades=15,
        max_daily_loss_pct=0.03,
        cooldown_after_loss_seconds=600,
    )

    print("\n策略配置:")
    print(f"  - 最小信号强度: {config.min_signal_strength.name}")
    print(f"  - 最小信号置信度: {config.min_signal_confidence:.0%}")
    print(f"  - 默认执行策略: {config.default_execution_strategy.name}")
    print(f"  - DCA批次: {config.dca_batches}")
    print(f"  - 每日最大交易: {config.max_daily_trades}")

    print("\n注意: 这是一个高级配置示例，展示了各种可配置参数。")
    print("实际使用时，需要根据具体策略和市场情况进行调整。")


# ==================== 运行示例 ====================

if __name__ == "__main__":
    print("买入策略使用示例")
    print("=" * 60)

    # 运行主示例
    asyncio.run(main())

    # 运行高级示例
    asyncio.run(advanced_example())
