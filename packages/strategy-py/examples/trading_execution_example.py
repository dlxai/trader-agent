"""
交易执行模块使用示例

该示例展示了如何使用 BuyStrategy、ExecutionEngine 和 SignalEvaluator
来实现完整的交易决策和执行流程。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入策略模块
from strategy import (
    # Buy Strategy
    BuyStrategy, BuyStrategyConfig, BuyDecision, BuyDecisionOutput,
    SignalStrength, MarketContext, OddsBiasMetrics, TimeDecayMetrics,
    OrderbookPressureMetrics, CapitalFlowMetrics, InformationEdgeMetrics,

    # Execution Engine
    ExecutionEngine, ExecutionConfig, OrderType,

    # Signal Evaluator
    SignalEvaluator, SignalEvaluationConfig, SignalDirection,
    SignalRecord, SignalOutcome, SignalQuality,
    create_default_signal_evaluator,

    # Signal Generator
    SignalGenerator,
)


# ============================================================================
# 示例1: 基础的买入策略使用
# ============================================================================

async def example_basic_buy_strategy():
    """基础买入策略使用示例"""
    logger.info("=" * 60)
    logger.info("示例1: 基础买入策略使用")
    logger.info("=" * 60)

    # 1. 创建策略配置
    config = BuyStrategyConfig(
        # 死亡区间配置
        death_zone_min=0.60,
        death_zone_max=0.85,

        # 权重配置
        odds_bias_weight=0.25,
        time_decay_weight=0.15,
        orderbook_weight=0.20,
        capital_flow_weight=0.20,
        information_edge_weight=0.20,

        # 决策阈值
        strong_buy_threshold=0.80,
        buy_threshold=0.65,
        hold_threshold=0.45,

        # 仓位管理
        max_single_position_pct=0.10,
        max_total_positions=20
    )

    # 2. 创建模拟的信号生成器
    def momentum_signal_generator(context: MarketContext) -> Tuple[SignalStrength, float, str]:
        """动量信号生成器示例"""
        # 基于订单簿压力的简单动量逻辑
        if context.orderbook_pressure and context.orderbook_pressure.is_buying_pressure(0.3):
            return SignalStrength.STRONG, 0.8, "Strong buying pressure detected"
        elif context.current_price < 0.5:
            return SignalStrength.MODERATE, 0.6, "Price below 0.5, potential value"
        return SignalStrength.WEAK, 0.4, "No clear momentum"

    def value_signal_generator(context: MarketContext) -> Tuple[SignalStrength, float, str]:
        """价值信号生成器示例"""
        if context.odds_bias and context.odds_bias.is_favorable(0.05):
            edge = context.odds_bias.edge
            return SignalStrength.STRONG, min(0.9, 0.5 + edge * 5), f"Value edge: {edge:.2%}"
        return SignalStrength.NONE, 0.0, "No value opportunity"

    signal_generators = [momentum_signal_generator, value_signal_generator]

    # 3. 创建风险模拟器（实际使用时应传入真实的RiskManager）
    class MockRiskManager:
        async def check_position_limits(self, market_id: str):
            return {'allowed': True}

        async def check_daily_loss_limit(self):
            return {'allowed': True}

        async def check_correlation(self, market_id: str):
            return {'high_correlation': False}

    risk_manager = MockRiskManager()

    # 4. 创建买入策略
    buy_strategy = BuyStrategy(
        signal_generators=signal_generators,
        risk_manager=risk_manager,
        config=config
    )

    # 5. 创建市场环境上下文
    market_context = MarketContext(
        market_id="market-123",
        outcome_id="outcome-456",
        current_price=0.45,
        current_odds=2.22,
        timestamp=datetime.now(),
        volume_24h=150000,
        liquidity=50000,

        # 赔率偏向指标
        odds_bias=OddsBiasMetrics(
            implied_probability=0.45,
            estimated_true_probability=0.52,
            edge=0.07,
            confidence=0.75
        ),

        # 时间衰减指标
        time_decay=TimeDecayMetrics(
            time_to_expiry=timedelta(days=7),
            theta_decay_rate=0.02,
            optimal_holding_period=timedelta(days=5),
            urgency_score=0.6
        ),

        # 订单簿压力指标
        orderbook_pressure=OrderbookPressureMetrics(
            bid_ask_spread=0.002,
            bid_depth=25000,
            ask_depth=15000,
            imbalance_ratio=0.4,
            price_impact=0.005
        ),

        # 资金流向指标
        capital_flow=CapitalFlowMetrics(
            smart_money_flow=0.6,
            retail_flow=-0.2,
            institutional_flow=0.4,
            flow_strength=0.7,
            trend_alignment=0.5
        ),

        # 信息优势指标
        information_edge=InformationEdgeMetrics(
            price_volume_divergence=0.3,
            unusual_activity_score=0.6,
            news_sentiment=0.4,
            social_sentiment=0.3,
            composite_score=0.65
        )
    )

    # 6. 执行评估
    logger.info("Evaluating market context...")
    decision_output = await buy_strategy.evaluate(market_context)

    # 7. 输出结果
    logger.info("-" * 60)
    logger.info("决策结果:")
    logger.info(f"  决策: {decision_output.decision.value}")
    logger.info(f"  置信度: {decision_output.confidence:.2%}")
    logger.info(f"  建议仓位: {decision_output.position_size:.2%}")
    logger.info(f"  入场价格: {decision_output.entry_price}")
    if decision_output.stop_loss:
        logger.info(f"  止损: {decision_output.stop_loss}")
    if decision_output.take_profit:
        logger.info(f"  止盈: {decision_output.take_profit}")

    logger.info("\n决策理由:")
    for reason in decision_output.reasoning:
        logger.info(f"  - {reason}")

    if decision_output.risk_warnings:
        logger.info("\n风险警告:")
        for warning in decision_output.risk_warnings:
            logger.info(f"  - {warning}")

    logger.info("\n信号分数:")
    for signal_name, score in decision_output.signal_scores.items():
        logger.info(f"  - {signal_name}: {score:.3f}")

    return buy_strategy, decision_output


# ============================================================================
# 示例2: 执行引擎的使用
# ============================================================================

async def example_execution_engine(buy_strategy, decision_output):
    """执行引擎使用示例"""
    logger.info("\n" + "=" * 60)
    logger.info("示例2: 执行引擎使用")
    logger.info("=" * 60)

    # 1. 创建模拟的订单管理器
    class MockOrderManager:
        def __init__(self):
            self.orders = {}
            self.order_counter = 0

        async def place_order(self, order_data):
            self.order_counter += 1
            order_id = f"order_{self.order_counter}"

            # 模拟订单执行
            size = order_data.get('size', 0)
            price = order_data.get('price', 0.45)

            result = {
                'order_id': order_id,
                'client_order_id': order_data.get('client_order_id'),
                'status': 'filled',
                'filled_size': size,
                'remaining_size': 0,
                'avg_fill_price': price * (1 + 0.001),  # 模拟轻微滑点
                'total_cost': size * price * (1 + 0.001),
                'fees': size * price * 0.001,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            self.orders[order_id] = result
            return result

        async def place_market_order(self, market_id, outcome_id, side, size, client_order_id=None):
            return await self.place_order({
                'market_id': market_id,
                'outcome_id': outcome_id,
                'side': side,
                'order_type': 'market',
                'size': size,
                'client_order_id': client_order_id
            })

        async def place_limit_order(self, market_id, outcome_id, side, size, price,
                                    time_in_force='GTC', client_order_id=None):
            return await self.place_order({
                'market_id': market_id,
                'outcome_id': outcome_id,
                'side': side,
                'order_type': 'limit',
                'size': size,
                'price': price,
                'time_in_force': time_in_force,
                'client_order_id': client_order_id
            })

    # 2. 创建模拟的持仓跟踪器
    class MockPositionTracker:
        def __init__(self):
            self.positions = {}

        async def add_position(self, position_data):
            key = f"{position_data['market_id']}_{position_data['outcome_id']}"
            self.positions[key] = position_data
            logger.info(f"Position added: {key}")

    # 3. 创建模拟的风险管理器
    class MockRiskManager:
        async def check_position_limits(self, market_id):
            return {'allowed': True}

        async def check_daily_loss_limit(self):
            return {'allowed': True}

        async def check_correlation(self, market_id):
            return {'high_correlation': False}

    # 4. 创建执行引擎
    execution_config = ExecutionConfig(
        preferred_order_type=OrderType.LIMIT,
        fallback_to_market=True,
        default_limit_offset=0.001,
        max_slippage_tolerance=0.02,
        allow_partial_fills=True,
        min_fill_threshold=0.5
    )

    execution_engine = ExecutionEngine(
        order_manager=MockOrderManager(),
        risk_manager=MockRiskManager(),
        position_tracker=MockPositionTracker(),
        config=execution_config
    )

    # 5. 执行买入决策
    logger.info("\n开始执行买入决策...")

    if decision_output.decision.value in ['strong_buy', 'buy']:
        execution_report = await execution_engine.execute_buy(decision_output)

        # 6. 输出执行结果
        logger.info("-" * 60)
        logger.info("执行结果:")
        logger.info(f"  执行ID: {execution_report.execution_id}")
        logger.info(f"  状态: {execution_report.status.value}")
        logger.info(f"  订单提交: {execution_report.orders_submitted}")
        logger.info(f"  订单成交: {execution_report.orders_filled}")
        logger.info(f"  成交数量: {execution_report.filled_size:.4f}")
        logger.info(f"  平均成交价格: {execution_report.avg_fill_price:.4f}")
        logger.info(f"  总成本: {execution_report.total_cost:.2f}")
        logger.info(f"  滑点: {execution_report.slippage:.4%}")

        if execution_report.errors:
            logger.info("\n错误:")
            for error in execution_report.errors:
                logger.info(f"  - {error}")

        if execution_report.warnings:
            logger.info("\n警告:")
            for warning in execution_report.warnings:
                logger.info(f"  - {warning}")

        # 显示执行统计
        stats = execution_engine.get_stats()
        logger.info("\n执行统计:")
        logger.info(f"  总执行次数: {stats['total_executions']}")
        logger.info(f"  成功次数: {stats['successful_executions']}")
        logger.info(f"  失败次数: {stats['failed_executions']}")
        logger.info(f"  总交易量: {stats['total_volume']:.4f}")
        logger.info(f"  平均滑点: {stats['avg_slippage']:.4%}")

        return execution_engine, execution_report
    else:
        logger.info(f"决策为 {decision_output.decision.value}，不执行买入")
        return execution_engine, None


# ============================================================================
# 示例3: 信号评估器的使用
# ============================================================================

async def example_signal_evaluator():
    """信号评估器使用示例"""
    logger.info("\n" + "=" * 60)
    logger.info("示例3: 信号评估器使用")
    logger.info("=" * 60)

    # 1. 创建信号评估器
    evaluator = create_default_signal_evaluator()

    # 2. 配置评估参数
    evaluator.config = SignalEvaluationConfig(
        min_samples_for_metrics=5,
        min_accuracy_threshold=0.55,
        min_sharpe_threshold=0.5,
        enable_dynamic_weighting=True
    )

    # 3. 模拟一些信号记录和结果
    signal_records = [
        SignalRecord(
            signal_id="sig_001",
            signal_name="momentum_signal",
            market_id="market_A",
            outcome_id="outcome_1",
            direction=SignalDirection.BUY,
            strength=0.8,
            timestamp=datetime.now() - timedelta(days=10),
            predicted_direction=SignalDirection.BUY,
            confidence=0.75
        ),
        SignalRecord(
            signal_id="sig_002",
            signal_name="momentum_signal",
            market_id="market_B",
            outcome_id="outcome_2",
            direction=SignalDirection.BUY,
            strength=0.7,
            timestamp=datetime.now() - timedelta(days=8),
            predicted_direction=SignalDirection.BUY,
            confidence=0.70
        ),
        SignalRecord(
            signal_id="sig_003",
            signal_name="value_signal",
            market_id="market_C",
            outcome_id="outcome_1",
            direction=SignalDirection.BUY,
            strength=0.9,
            timestamp=datetime.now() - timedelta(days=5),
            predicted_direction=SignalDirection.BUY,
            confidence=0.85
        ),
    ]

    signal_outcomes = [
        SignalOutcome(
            signal_id="sig_001",
            market_id="market_A",
            outcome_id="outcome_1",
            actual_direction=SignalDirection.BUY,
            actual_return=0.15,
            realized_pnl=150.0,
            signal_timestamp=datetime.now() - timedelta(days=10),
            outcome_timestamp=datetime.now() - timedelta(days=7),
            time_to_outcome=timedelta(days=3),
            prediction_correct=True,
            accuracy_score=0.85,
            profitability_score=0.80
        ),
        SignalOutcome(
            signal_id="sig_002",
            market_id="market_B",
            outcome_id="outcome_2",
            actual_direction=SignalDirection.SELL,
            actual_return=-0.05,
            realized_pnl=-50.0,
            signal_timestamp=datetime.now() - timedelta(days=8),
            outcome_timestamp=datetime.now() - timedelta(days=5),
            time_to_outcome=timedelta(days=3),
            prediction_correct=False,
            accuracy_score=0.30,
            profitability_score=0.20
        ),
        SignalOutcome(
            signal_id="sig_003",
            market_id="market_C",
            outcome_id="outcome_1",
            actual_direction=SignalDirection.BUY,
            actual_return=0.22,
            realized_pnl=220.0,
            signal_timestamp=datetime.now() - timedelta(days=5),
            outcome_timestamp=datetime.now() - timedelta(days=2),
            time_to_outcome=timedelta(days=3),
            prediction_correct=True,
            accuracy_score=0.95,
            profitability_score=0.90
        ),
    ]

    # 4. 记录信号和结果
    for record in signal_records:
        await evaluator.record_signal(record)

    for outcome in signal_outcomes:
        await evaluator.record_outcome(outcome)

    # 5. 获取信号指标
    logger.info("\n信号指标评估结果:")
    logger.info("-" * 60)

    for signal_name in ["momentum_signal", "value_signal"]:
        metrics = evaluator.get_signal_metrics(signal_name)
        if metrics:
            logger.info(f"\n信号: {signal_name}")
            logger.info(f"  总信号数: {metrics.total_signals}")
            logger.info(f"  准确率: {metrics.accuracy:.2%}")
            logger.info(f"  精确率: {metrics.precision:.2%}")
            logger.info(f"  召回率: {metrics.recall:.2%}")
            logger.info(f"  F1分数: {metrics.f1_score:.3f}")
            logger.info(f"  平均回报: {metrics.avg_return:.2%}")
            logger.info(f"  夏普比率: {metrics.sharpe_ratio:.3f}")
            logger.info(f"  胜率: {metrics.win_rate:.2%}")
            logger.info(f"  盈亏比: {metrics.profit_factor:.2f}")
            logger.info(f"  最大回撤: {metrics.max_drawdown:.2%}")
            logger.info(f"  质量评级: {metrics.quality.value}")
            logger.info(f"  置信度: {metrics.confidence:.2%}")

    # 6. 获取信号权重
    logger.info("\n信号权重:")
    logger.info("-" * 60)
    weights = evaluator.get_all_weights()
    normalized = evaluator.normalize_weights()
    for signal_name in weights:
        logger.info(f"  {signal_name}: {weights[signal_name]:.3f} (normalized: {normalized.get(signal_name, 0):.3f})")

    # 7. 获取顶级信号
    logger.info("\n顶级信号（按夏普比率排序）:")
    logger.info("-" * 60)
    top_signals = evaluator.get_top_signals(n=3, criterion="sharpe_ratio")
    for signal_name, metrics in top_signals:
        logger.info(f"  {signal_name}: Sharpe={metrics.sharpe_ratio:.3f}, WinRate={metrics.win_rate:.2%}")

    # 8. 获取优化建议
    logger.info("\n信号优化建议:")
    logger.info("-" * 60)
    recommendations = evaluator.get_signal_recommendations()

    if recommendations['add_signals']:
        logger.info("建议添加的信号:")
        for rec in recommendations['add_signals']:
            logger.info(f"  - {rec['suggestion']}: {rec['rationale']}")

    if recommendations['remove_signals']:
        logger.info("建议移除的信号:")
        for rec in recommendations['remove_signals']:
            logger.info(f"  - {rec['signal']}: {rec['reason']}")

    if recommendations['adjust_weights']:
        logger.info("建议调整的权重:")
        for signal, adjustment in recommendations['adjust_weights'].items():
            logger.info(f"  - {signal}: {adjustment['current']:.3f} -> {adjustment['target']:.3f}")

    if recommendations['improve_timing']:
        logger.info("建议改进的时效性:")
        for rec in recommendations['improve_timing']:
            logger.info(f"  - {rec['signal']}: {rec['suggestion']}")

    return evaluator


# ============================================================================
# 主函数
# ============================================================================

async def main():
    """主函数 - 运行所有示例"""
    logger.info("\n" + "=" * 60)
    logger.info("交易执行模块使用示例")
    logger.info("=" * 60)

    try:
        # 运行示例1: 买入策略
        buy_strategy, decision_output = await example_basic_buy_strategy()

        # 运行示例2: 执行引擎（如果决策是买入）
        if decision_output and decision_output.decision.value in ['strong_buy', 'buy']:
            execution_engine, execution_report = await example_execution_engine(
                buy_strategy, decision_output
            )

        # 运行示例3: 信号评估器
        evaluator = await example_signal_evaluator()

        logger.info("\n" + "=" * 60)
        logger.info("所有示例运行完成！")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"运行示例时发生错误: {e}")
        raise


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
