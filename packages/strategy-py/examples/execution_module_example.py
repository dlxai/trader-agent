"""
交易执行模块使用示例

该示例展示了如何使用买入策略、执行引擎和信号评估器。
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# 导入策略模块
from strategy import (
    # 买入策略
    BuyStrategy,
    BuyStrategyConfig,
    BuyDecision,
    Signal,
    SignalType,
    MarketCondition,
    RiskLevel,
    # 执行引擎
    ExecutionEngine,
    ExecutionConfig,
    ExecutionReport,
    Order,
    OrderType,
    OrderStatus,
    ExecutionResult,
    # 信号评估器
    SignalEvaluator,
    SignalMetrics,
    SignalWeights,
    create_signal_evaluator,
)


# =============================================================================
# 模拟组件实现
# =============================================================================

class MockSignalGenerator:
    """模拟信号生成器"""

    def __init__(self, signal_type: SignalType, bias: float = 0.0):
        self.signal_type = signal_type
        self.bias = bias

    async def generate(self, market_condition: MarketCondition) -> Signal:
        """生成模拟信号"""
        import random

        # 基于市场条件生成信号分数
        base_score = random.uniform(-0.3, 0.3) + self.bias

        # 根据信号类型调整
        if self.signal_type == SignalType.ODDS_BIAS:
            # 赔率偏向：价格偏离0.5越远，信号越强
            deviation = abs(float(market_condition.current_price) - 0.5)
            base_score += deviation * 2 - 0.5

        elif self.signal_type == SignalType.TIME_DECAY:
            # 时间衰减：到期时间越短，时间价值越小
            hours_left = market_condition.time_to_resolution.total_seconds() / 3600
            if hours_left < 24:
                base_score += 0.2
            elif hours_left > 168:  # 7天
                base_score -= 0.1

        elif self.signal_type == SignalType.ORDERBOOK_PRESSURE:
            # 订单簿压力：买卖价差和深度
            if market_condition.spread_pct < 0.01:  # 窄价差
                base_score += 0.15
            if market_condition.liquidity_depth > Decimal("10000"):
                base_score += 0.1

        # 限制分数范围
        score = max(-1.0, min(1.0, base_score))

        # 置信度基于市场条件稳定性
        confidence = 0.5 + (0.5 - market_condition.volatility)
        confidence = max(0.1, min(1.0, confidence))

        return Signal(
            signal_type=self.signal_type,
            score=score,
            confidence=confidence,
            metadata={
                "market_price": str(market_condition.current_price),
                "volatility": market_condition.volatility,
            }
        )


class MockRiskManager:
    """模拟风险管理器"""

    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.total_exposure = Decimal("0")

    async def check_death_zone(self, price: Decimal) -> bool:
        """检查是否在死亡区间 ($0.60-$0.85)"""
        death_zone_low = Decimal("0.60")
        death_zone_high = Decimal("0.85")
        return death_zone_low <= price <= death_zone_high

    async def check_position_limits(
        self,
        market_id: str,
        size: Decimal
    ) -> Tuple[bool, str]:
        """检查持仓限制"""
        current_position = self.positions.get(market_id, {})
        current_size = Decimal(str(current_position.get("size", 0)))
        max_position = Decimal("1000")  # $1000 单笔上限

        if current_size + size > max_position:
            return False, f"Would exceed max position size {max_position}"

        return True, "Position limits OK"

    async def calculate_correlation_risk(self, market_id: str) -> float:
        """计算相关性风险（模拟）"""
        # 简化实现，实际应该基于历史价格数据计算
        return 0.3  # 假设中等相关性

    async def get_total_exposure(self) -> Decimal:
        """获取总敞口"""
        return self.total_exposure


class MockPositionTracker:
    """模拟持仓跟踪器"""

    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}

    async def get_position(self, market_id: str) -> Optional[Dict[str, Any]]:
        """获取持仓信息"""
        return self.positions.get(market_id)

    async def update_position(
        self,
        market_id: str,
        update: Dict[str, Any]
    ) -> None:
        """更新持仓"""
        self.positions[market_id] = update


class MockOrderManager:
    """模拟订单管理器"""

    def __init__(self):
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.order_counter = 0

    async def submit_order(self, order: Dict[str, Any]) -> str:
        """提交订单"""
        self.order_counter += 1
        order_id = f"mock-order-{self.order_counter}"

        self.orders[order_id] = {
            **order,
            "order_id": order_id,
            "status": "submitted",
            "filled_size": "0",
            "created_at": datetime.now().isoformat(),
        }

        # 模拟异步成交
        asyncio.create_task(self._simulate_fill(order_id))

        return order_id

    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "cancelled"
            return True
        return False

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """获取订单状态"""
        return self.orders.get(order_id, {})

    async def _simulate_fill(self, order_id: str) -> None:
        """模拟订单成交"""
        await asyncio.sleep(1)  # 延迟1秒

        if order_id in self.orders:
            order = self.orders[order_id]
            if order.get("status") != "cancelled":
                # 模拟部分或全部成交
                import random
                fill_pct = random.uniform(0.8, 1.0)
                size = Decimal(order.get("size", "0"))
                filled_size = size * Decimal(str(fill_pct))

                order["status"] = "filled" if fill_pct >= 1.0 else "partial_fill"
                order["filled_size"] = str(filled_size)
                order["avg_fill_price"] = order.get("price") or "0.5"


# =============================================================================
# 示例使用代码
# =============================================================================

async def example_buy_strategy():
    """买入策略使用示例"""
    print("=" * 60)
    print("买入策略示例")
    print("=" * 60)

    # 创建模拟组件
    risk_manager = MockRiskManager()

    # 创建信号生成器
    signal_generators = [
        MockSignalGenerator(SignalType.ODDS_BIAS, bias=0.1),
        MockSignalGenerator(SignalType.TIME_DECAY, bias=0.05),
        MockSignalGenerator(SignalType.ORDERBOOK_PRESSURE, bias=0.0),
        MockSignalGenerator(SignalType.CAPITAL_FLOW, bias=0.05),
        MockSignalGenerator(SignalType.INFORMATION_EDGE, bias=0.0),
    ]

    # 创建策略配置
    config = BuyStrategyConfig(
        min_composite_score=0.5,
        min_confidence=0.6,
        max_position_size_usd=Decimal("500"),
        max_total_exposure_usd=Decimal("2000"),
    )

    # 创建买入策略
    strategy = BuyStrategy(
        signal_generators=signal_generators,
        risk_manager=risk_manager,
        config=config,
    )

    # 创建市场条件
    market_condition = MarketCondition(
        market_id="0x1234567890abcdef",
        current_price=Decimal("0.35"),
        best_bid=Decimal("0.34"),
        best_ask=Decimal("0.36"),
        volume_24h=Decimal("50000"),
        liquidity_depth=Decimal("20000"),
        spread_pct=0.02,
        volatility=0.03,
        time_to_resolution=timedelta(days=3),
    )

    # 执行评估
    decision = await strategy.evaluate(market_condition)

    # 输出结果
    print(f"\n市场: {decision.market_id}")
    print(f"建议买入: {decision.should_buy}")
    print(f"方向: {decision.side}")
    print(f"建议仓位: ${decision.size}")
    print(f"建议价格: ${decision.price}")
    print(f"订单类型: {decision.order_type}")
    print(f"置信度: {decision.confidence:.2%}")
    print(f"综合评分: {decision.composite_score:.3f}")
    print(f"风险等级: {decision.risk_level.name}")
    print(f"决策理由: {decision.decision_reason}")

    print(f"\n信号详情:")
    for signal in decision.signals:
        print(f"  - {signal.signal_type.name}: "
              f"score={signal.score:+.3f}, confidence={signal.confidence:.2%}")

    return decision


async def example_execution_engine():
    """执行引擎使用示例"""
    print("\n" + "=" * 60)
    print("执行引擎示例")
    print("=" * 60)

    # 创建模拟组件
    order_manager = MockOrderManager()
    risk_manager = MockRiskManager()
    position_tracker = MockPositionTracker()

    # 创建执行配置
    config = ExecutionConfig(
        default_slippage_bps=50,
        max_slippage_bps=200,
        order_timeout_seconds=30,
        dry_run=False,  # 设置为True进行模拟
    )

    # 创建执行引擎
    engine = ExecutionEngine(
        order_manager=order_manager,
        risk_manager=risk_manager,
        position_tracker=position_tracker,
        config=config,
    )

    # 创建买入决策
    class MockBuyDecision:
        def __init__(self):
            self.market_id = "0x1234567890abcdef"
            self.should_buy = True
            self.side = "YES"
            self.size = Decimal("100")
            self.price = Decimal("0.35")
            self.order_type = "limit"
            self.confidence = 0.75
            self.composite_score = 0.68
            self.risk_level = RiskLevel.MEDIUM

    decision = MockBuyDecision()

    # 模拟市场条件
    class MockMarketCondition:
        def __init__(self):
            self.current_price = Decimal("0.35")
            self.volatility = 0.03

    market_condition = MockMarketCondition()

    # 执行买入决策
    print(f"\n执行买入决策:")
    print(f"  市场: {decision.market_id}")
    print(f"  方向: {decision.side}")
    print(f"  数量: {decision.size}")
    print(f"  价格: {decision.price}")

    report = await engine.execute_buy_decision(decision, market_condition)

    # 输出执行结果
    print(f"\n执行结果:")
    print(f"  订单ID: {report.order_id}")
    print(f"  状态: {report.status.value}")
    print(f"  结果: {report.result.name}")
    print(f"  请求数量: {report.requested_size}")
    print(f"  成交数量: {report.filled_size}")
    print(f"  成交率: {report.fill_percentage:.1f}%")
    print(f"  平均成交价格: {report.avg_fill_price}")
    print(f"  滑点: {report.slippage_bps} bps")
    print(f"  执行时间: {report.execution_time_ms} ms")

    return report


async def example_signal_evaluator():
    """信号评估器使用示例"""
    print("\n" + "=" * 60)
    print("信号评估器示例")
    print("=" * 60)

    # 创建内存数据库
    db_path = ":memory:"
    conn = sqlite3.connect(db_path)

    # 创建信号评估器
    evaluator = SignalEvaluator(
        db_connection=conn,
        signal_sources=[],
        market_data_provider=None,
    )

    # 模拟记录一些信号
    print("\n模拟记录信号历史...")

    import random

    signal_types = ["ODDS_BIAS", "TIME_DECAY", "ORDERBOOK_PRESSURE", "CAPITAL_FLOW", "INFORMATION_EDGE"]
    outcomes = ["YES", "NO"]

    for i in range(100):
        signal_type = random.choice(signal_types)
        market_id = f"0x{random.randint(1000000000000000, 9999999999999999):x}"
        side = random.choice(outcomes)
        confidence = random.uniform(0.5, 0.95)
        score = random.uniform(-1.0, 1.0)
        predicted = random.choice(outcomes)

        record_id = evaluator.record_signal(
            signal_type=signal_type,
            market_id=market_id,
            side=side,
            confidence=confidence,
            score=score,
            predicted_outcome=predicted,
        )

        # 80%的信号有结果
        if random.random() < 0.8:
            actual = predicted if random.random() < 0.7 else random.choice(outcomes)
            pnl = Decimal(str(random.uniform(-50, 100))) if actual == predicted else Decimal(str(random.uniform(-100, 50)))

            evaluator.update_signal_result(record_id, actual, pnl)

    print("  记录了100个模拟信号")

    # 评估特定信号类型
    print("\n评估 ODDS_BIAS 信号...")
    metrics = await evaluator.evaluate_signal("ODDS_BIAS", lookback_days=30)

    print(f"  信号类型: {metrics.signal_type}")
    print(f"  准确率: {metrics.accuracy:.2%}")
    print(f"  夏普比率: {metrics.sharpe_ratio:.3f}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  盈亏比: {metrics.profit_factor:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")
    print(f"  质量分数: {metrics.quality_score:.3f}")
    print(f"  质量等级: {metrics.quality_grade.name}")
    print(f"  总信号数: {metrics.total_signals}")
    print(f"  盈利信号数: {metrics.profitable_signals}")

    # 优化信号权重
    print("\n优化信号权重...")
    weights = await evaluator.optimize_weights(
        lookback_days=30,
        method="performance_based"
    )

    print("  优化后的权重:")
    for signal_type, weight in weights.weights.items():
        print(f"    {signal_type}: {weight:.3f}")
    print(f"  优化方法: {weights.optimization_method}")
    print(f"  最后更新: {weights.last_updated}")

    # 获取性能摘要
    print("\n性能摘要:")
    summary = evaluator.get_performance_summary(
        start_date=datetime.now() - timedelta(days=30),
        end_date=datetime.now()
    )

    print(f"  总信号数: {summary.get('total_signals', 0)}")
    print(f"  完成信号数: {summary.get('completed_signals', 0)}")
    print(f"  准确率: {summary.get('accuracy', 0):.2%}")
    print(f"  胜率: {summary.get('win_rate', 0):.2%}")
    print(f"  平均盈亏: ${summary.get('avg_pnl', 0):.2f}")

    # 清理
    conn.close()

    return evaluator


# =============================================================================
# 主函数
# =============================================================================

async def main():
    """主函数 - 运行所有示例"""
    print("\n" + "=" * 60)
    print("交易执行模块示例")
    print("=" * 60)

    try:
        # 运行买入策略示例
        await example_buy_strategy()

        # 运行执行引擎示例
        await example_execution_engine()

        # 运行信号评估器示例
        await example_signal_evaluator()

        print("\n" + "=" * 60)
        print("所有示例运行完成!")
        print("=" * 60)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
