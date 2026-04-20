"""
资金流分析辅助决策系统 - 单元测试

测试模块：
1. CapitalFlowCollector - 资金流数据收集器
2. FlowSignalCalculator - 资金流信号计算器
3. FlowAssistedDecision - 辅助决策引擎
4. FlowAnalytics - 统计和报告模块
5. CapitalFlowAssistedExit - 集成系统
"""

import unittest
import random
import numpy as np
from datetime import datetime, timedelta
from typing import List

import sys
sys.path.insert(0, 'packages/strategy-py/src')

from strategy.capital_flow_analyzer import (
    # 主类
    CapitalFlowAssistedExit,
    CapitalFlowCollector,
    FlowSignalCalculator,
    FlowAssistedDecision,
    FlowAnalytics,

    # 枚举类型
    FlowDirection,
    SignalStrength,
    DecisionAction,

    # 数据结构
    TradeRecord,
    FlowMetrics,
    FlowSignal,
    DecisionResult,
    PerformanceMetrics,

    # 便捷函数
    create_default_system,
)


# =============================================================================
# 测试 CapitalFlowCollector
# =============================================================================

class TestCapitalFlowCollector(unittest.TestCase):
    """测试资金流数据收集器"""

    def setUp(self):
        """设置测试环境"""
        self.collector = CapitalFlowCollector(
            windows=[60, 300],
            max_history=1000
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.collector.windows, [60, 300])
        self.assertEqual(self.collector.max_history, 1000)
        self.assertEqual(len(self.collector._trades), 0)

    def test_add_trade(self):
        """测试添加单笔交易"""
        timestamp = datetime.now()
        self.collector.add_trade(
            timestamp=timestamp,
            price=0.55,
            size=100,
            side="buy",
            trader_id="trader_001"
        )

        self.assertEqual(len(self.collector._trades), 1)
        trade = self.collector._trades[0]
        self.assertEqual(trade.price, 0.55)
        self.assertEqual(trade.size, 100)
        self.assertEqual(trade.side, "buy")

    def test_add_trades_batch(self):
        """测试批量添加交易"""
        trades = [
            {
                "timestamp": datetime.now() - timedelta(minutes=i),
                "price": 0.5 + i * 0.01,
                "size": 50 + i * 10,
                "side": "buy" if i % 2 == 0 else "sell",
                "trader_id": f"trader_{i % 5}"
            }
            for i in range(20)
        ]

        self.collector.add_trades_batch(trades)
        self.assertEqual(len(self.collector._trades), 20)

    def test_get_flow_metrics(self):
        """测试获取资金流指标"""
        # 添加测试数据
        base_time = datetime.now() - timedelta(minutes=10)
        for i in range(60):
            self.collector.add_trade(
                timestamp=base_time + timedelta(seconds=i * 10),
                price=0.5 + random.uniform(-0.02, 0.02),
                size=random.uniform(10, 50),
                side="buy" if random.random() > 0.4 else "sell",
                trader_id=f"trader_{i % 10}"
            )

        metrics = self.collector.get_flow_metrics(window_seconds=60)

        self.assertIsInstance(metrics, FlowMetrics)
        self.assertEqual(metrics.window_seconds, 60)
        self.assertIsNotNone(metrics.net_flow)
        self.assertIsNotNone(metrics.inflow)
        self.assertIsNotNone(metrics.outflow)

    def test_get_flow_distribution(self):
        """测试获取资金流分布"""
        # 添加足够的数据
        base_time = datetime.now() - timedelta(hours=1)
        for i in range(100):
            self.collector.add_trade(
                timestamp=base_time + timedelta(minutes=i),
                price=0.5 + random.uniform(-0.05, 0.05),
                size=random.uniform(20, 100),
                side="buy" if random.random() > 0.5 else "sell",
                trader_id=f"trader_{i % 20}"
            )

        distribution = self.collector.get_flow_distribution(window_seconds=3600, bins=10)

        self.assertIn("data_points", distribution)
        self.assertIn("mean", distribution)
        self.assertIn("std", distribution)


# =============================================================================
# 测试 FlowSignalCalculator
# =============================================================================

class TestFlowSignalCalculator(unittest.TestCase):
    """测试资金流信号计算器"""

    def setUp(self):
        """设置测试环境"""
        self.calculator = FlowSignalCalculator(
            history_window=100,
            acceleration_lookback=3,
            extreme_std_threshold=2.0,
            consecutive_threshold=3
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.calculator.history_window, 100)
        self.assertEqual(self.calculator.acceleration_lookback, 3)
        self.assertEqual(self.calculator.extreme_std_threshold, 2.0)

    def test_add_minute_flow(self):
        """测试添加分钟资金流"""
        timestamp = datetime.now()
        self.calculator.add_minute_flow(timestamp, 100.0)

        self.assertEqual(len(self.calculator._minute_flows), 1)
        self.assertEqual(len(self.calculator._flow_history), 1)

    def test_acceleration_detection(self):
        """测试加速信号检测"""
        # 添加加速的负向资金流（连续3分钟）
        base_time = datetime.now() - timedelta(minutes=5)

        # 正常资金流
        self.calculator.add_minute_flow(base_time, 50.0)
        self.calculator.add_minute_flow(base_time + timedelta(minutes=1), -30.0)

        # 加速负向资金流
        self.calculator.add_minute_flow(base_time + timedelta(minutes=2), -100.0)
        self.calculator.add_minute_flow(base_time + timedelta(minutes=3), -200.0)
        self.calculator.add_minute_flow(base_time + timedelta(minutes=4), -350.0)

        signals = self.calculator.calculate_signals()

        # 应该检测到加速信号
        accel_signals = [s for s in signals if s.signal_type == "acceleration"]
        self.assertGreater(len(accel_signals), 0)

        # 检查方向是否正确
        if accel_signals:
            self.assertEqual(accel_signals[0].direction, FlowDirection.NEGATIVE)

    def test_extreme_flow_detection(self):
        """测试极端流检测"""
        # 添加正常分布的数据
        base_time = datetime.now() - timedelta(minutes=50)

        for i in range(40):
            # 正常分布的数据
            flow = random.gauss(0, 50)
            self.calculator.add_minute_flow(
                base_time + timedelta(minutes=i),
                flow
            )

        # 添加极端值
        self.calculator.add_minute_flow(
            base_time + timedelta(minutes=40),
            300  # 极端正值（> 2σ）
        )

        signals = self.calculator.calculate_signals()

        # 应该检测到极端信号
        extreme_signals = [s for s in signals if s.signal_type == "extreme_flow"]
        self.assertGreater(len(extreme_signals), 0)


# =============================================================================
# 测试 FlowAssistedDecision
# =============================================================================

class TestFlowAssistedDecision(unittest.TestCase):
    """测试辅助决策引擎"""

    def setUp(self):
        """设置测试环境"""
        self.decision = FlowAssistedDecision(
            weights={
                "price_based_exit": 0.7,
                "flow_acceleration": 0.3,
            },
            confidence_threshold=0.6,
            enable_extreme_override=True
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.decision.weights["price_based_exit"], 0.7)
        self.assertEqual(self.decision.weights["flow_acceleration"], 0.3)
        self.assertEqual(self.decision.confidence_threshold, 0.6)

    def test_make_decision_price_only(self):
        """测试仅价格信号的决策"""
        price_signal = {
            "type": "stop_loss",
            "trigger_price": 0.45,
            "loss_pct": -0.10
        }

        result = self.decision.make_decision(
            position_id="pos_test_001",
            price_signal=price_signal,
            flow_signals=[]
        )

        self.assertEqual(result.position_id, "pos_test_001")
        self.assertIn(result.action, [DecisionAction.EXIT_IMMEDIATELY, DecisionAction.ACCELERATE_EXIT])
        self.assertGreater(result.confidence, 0)

    def test_make_decision_with_flow_signals(self):
        """测试带资金流信号的决策"""
        price_signal = {
            "type": "take_profit",
            "trigger_price": 0.65,
            "profit_pct": 0.20
        }

        flow_signals = [
            FlowSignal(
                timestamp=datetime.now(),
                signal_type="extreme_flow",
                direction=FlowDirection.NEGATIVE,
                strength=SignalStrength.EXTREME,
                confidence=0.9,
                metrics={"z_score": 3.5},
                description="极端负向资金流",
                suggested_action=DecisionAction.EXIT_IMMEDIATELY,
                priority=9
            )
        ]

        result = self.decision.make_decision(
            position_id="pos_test_002",
            price_signal=price_signal,
            flow_signals=flow_signals
        )

        # 应该触发退出
        self.assertEqual(result.action, DecisionAction.EXIT_IMMEDIATELY)
        self.assertEqual(result.exit_ratio, 1.0)

    def test_extreme_override(self):
        """测试极端情况覆盖"""
        # 创建一个会触发极端覆盖的场景
        price_signal = {
            "type": "stop_loss",
            "trigger_price": 0.45
        }

        flow_signals = [
            FlowSignal(
                timestamp=datetime.now(),
                signal_type="extreme_flow",
                direction=FlowDirection.NEGATIVE,
                strength=SignalStrength.EXTREME,
                confidence=0.95,
                metrics={},
                description="极端负向",
                suggested_action=DecisionAction.EXIT_IMMEDIATELY,
                priority=10
            )
        ]

        result = self.decision.make_decision(
            position_id="pos_test_003",
            price_signal=price_signal,
            flow_signals=flow_signals
        )

        # 极端情况应该触发立即退出
        self.assertEqual(result.action, DecisionAction.EXIT_IMMEDIATELY)


# =============================================================================
# 测试 FlowAnalytics
# =============================================================================

class TestFlowAnalytics(unittest.TestCase):
    """测试统计和报告模块"""

    def setUp(self):
        """设置测试环境"""
        self.analytics = FlowAnalytics(
            performance_window=500,
            backtest_enabled=True,
            realtime_dashboard=True
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.analytics.performance_window, 500)
        self.assertTrue(self.analytics.backtest_enabled)
        self.assertTrue(self.analytics.realtime_dashboard)

    def test_record_prediction(self):
        """测试记录预测"""
        # 记录正确预测（真阳性）
        self.analytics.record_prediction(
            prediction={"is_positive": True, "confidence": 0.8},
            actual_outcome=True
        )

        # 记录错误预测（假阳性）
        self.analytics.record_prediction(
            prediction={"is_positive": True, "confidence": 0.7},
            actual_outcome=False
        )

        # 记录正确预测（真阴性）
        self.analytics.record_prediction(
            prediction={"is_positive": False, "confidence": 0.9},
            actual_outcome=False
        )

        # 验证统计
        self.assertEqual(self.analytics._performance.total_predictions, 3)
        self.assertEqual(self.analytics._performance.true_positives, 1)
        self.assertEqual(self.analytics._performance.false_positives, 1)
        self.assertEqual(self.analytics._performance.true_negatives, 1)

        # 验证计算指标
        self.assertAlmostEqual(self.analytics._performance.accuracy, 2/3)
        self.assertAlmostEqual(self.analytics._performance.precision, 0.5)

    def test_record_signal(self):
        """测试记录信号"""
        signal = FlowSignal(
            timestamp=datetime.now(),
            signal_type="acceleration",
            direction=FlowDirection.NEGATIVE,
            strength=SignalStrength.STRONG,
            confidence=0.85,
            metrics={"acceleration_rate": 2.5},
            description="测试信号",
            suggested_action=DecisionAction.ACCELERATE_EXIT,
            priority=7
        )

        self.analytics.record_signal(signal, outcome="correct")

        self.assertEqual(len(self.analytics._signal_history), 1)
        recorded = self.analytics._signal_history[0]
        self.assertEqual(recorded["signal"].signal_type, "acceleration")
        self.assertEqual(recorded["outcome"], "correct")

    def test_performance_summary(self):
        """测试性能摘要"""
        # 添加一些测试数据
        for i in range(10):
            self.analytics.record_prediction(
                prediction={"is_positive": i % 3 != 0, "confidence": 0.7 + i * 0.02},
                actual_outcome=i % 2 == 0
            )

        summary = self.analytics.get_performance_summary()

        self.assertIn("predictions", summary)
        self.assertIn("metrics", summary)
        self.assertIn("data_volumes", summary)

        self.assertEqual(summary["predictions"]["total"], 10)
        self.assertIn("accuracy", summary["metrics"])
        self.assertIn("f1_score", summary["metrics"])

    def test_realtime_dashboard(self):
        """测试实时监控面板"""
        dashboard = self.analytics.get_realtime_dashboard()

        # 即使数据为空，也应该返回基本结构
        self.assertIn("timestamp", dashboard)
        self.assertIn("performance", dashboard)

        # 添加一些数据后再测试
        for i in range(5):
            signal = FlowSignal(
                timestamp=datetime.now(),
                signal_type="test",
                direction=FlowDirection.POSITIVE,
                strength=SignalStrength.MODERATE,
                confidence=0.7,
                metrics={},
                description="Test",
                suggested_action=DecisionAction.NO_ACTION,
                priority=3
            )
            self.analytics.record_signal(signal)
            self.analytics.record_prediction(
                prediction={"is_positive": True, "confidence": 0.8},
                actual_outcome=True
            )

        dashboard = self.analytics.get_realtime_dashboard()
        self.assertIn("recent_signals", dashboard)
        self.assertEqual(len(dashboard["recent_signals"]), 5)


# =============================================================================
# 测试 CapitalFlowAssistedExit 集成系统
# =============================================================================

class TestCapitalFlowAssistedExit(unittest.TestCase):
    """测试集成系统"""

    def setUp(self):
        """设置测试环境"""
        self.exit_system = create_default_system(enabled=True)

    def test_initialization(self):
        """测试初始化"""
        self.assertTrue(self.exit_system.enabled)
        self.assertIsNotNone(self.exit_system.collector)
        self.assertIsNotNone(self.exit_system.calculator)
        self.assertIsNotNone(self.exit_system.decision)
        self.assertIsNotNone(self.exit_system.analytics)

    def test_create_default_system(self):
        """测试便捷创建函数"""
        system = create_default_system(
            enabled=True,
            custom_weights={"price_based_exit": 0.5, "flow_acceleration": 0.5}
        )

        self.assertTrue(system.enabled)
        self.assertEqual(system.decision.weights["price_based_exit"], 0.5)
        self.assertEqual(system.decision.weights["flow_acceleration"], 0.5)

    def test_register_position(self):
        """测试注册持仓"""
        self.exit_system.register_position(
            position_id="pos_test_001",
            entry_price=0.5,
            size=1000,
            side="long",
            metadata={"market": "BTC-USD"}
        )

        self.assertIn("pos_test_001", self.exit_system._positions)
        position = self.exit_system._positions["pos_test_001"]
        self.assertEqual(position["entry_price"], 0.5)
        self.assertEqual(position["size"], 1000)
        self.assertEqual(position["metadata"]["market"], "BTC-USD")

    def test_add_trade_and_flow_update(self):
        """测试添加交易和资金流的联动更新"""
        timestamp = datetime.now()

        # 添加交易
        self.exit_system.add_trade(
            timestamp=timestamp,
            price=0.55,
            size=100,
            side="buy",
            trader_id="trader_001"
        )

        # 验证收集器接收到数据
        self.assertEqual(len(self.exit_system.collector._trades), 1)

        # 验证计算器接收到分钟流
        # (因为 add_trade 会同时更新 calculator)
        self.assertEqual(len(self.exit_system.calculator._minute_flows), 1)

    def test_check_exit_conditions_disabled(self):
        """测试禁用状态下的退出检查"""
        disabled_system = create_default_system(enabled=False)

        result = disabled_system.check_exit_conditions(
            position_id="pos_test",
            current_price=0.6,
            price_signal=None
        )

        self.assertEqual(result.action, DecisionAction.NO_ACTION)
        self.assertEqual(result.exit_ratio, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_check_exit_conditions_with_price_signal(self):
        """测试带价格信号的退出检查"""
        # 注册持仓
        self.exit_system.register_position(
            position_id="pos_test_002",
            entry_price=0.5,
            size=100,
            side="long"
        )

        # 添加一些交易数据
        base_time = datetime.now() - timedelta(minutes=5)
        for i in range(30):
            self.exit_system.add_trade(
                timestamp=base_time + timedelta(seconds=i * 10),
                price=0.5 + i * 0.005,
                size=random.uniform(10, 30),
                side="buy" if i % 3 != 0 else "sell",
                trader_id=f"trader_{i % 5}"
            )

        # 价格止损信号
        price_signal = {
            "type": "stop_loss",
            "trigger_price": 0.45,
            "loss_pct": -0.10
        }

        result = self.exit_system.check_exit_conditions(
            position_id="pos_test_002",
            current_price=0.45,
            price_signal=price_signal
        )

        # 应该建议退出
        self.assertIn(result.action, [
            DecisionAction.EXIT_IMMEDIATELY,
            DecisionAction.ACCELERATE_EXIT
        ])
        self.assertGreater(result.confidence, 0)
        self.assertGreater(len(result.reasoning), 0)

    def test_get_realtime_dashboard(self):
        """测试获取实时监控面板"""
        # 添加一些数据
        base_time = datetime.now() - timedelta(minutes=10)
        for i in range(50):
            self.exit_system.add_trade(
                timestamp=base_time + timedelta(seconds=i * 12),
                price=0.5 + random.uniform(-0.05, 0.05),
                size=random.uniform(10, 50),
                side=random.choice(["buy", "sell"]),
                trader_id=f"trader_{i % 8}"
            )

        dashboard = self.exit_system.get_realtime_dashboard()

        self.assertIn("timestamp", dashboard)
        self.assertIn("flow_metrics", dashboard)
        self.assertIn("performance", dashboard)
        self.assertIn("system_status", dashboard)

    def test_generate_analytics_report(self):
        """测试生成分析报告"""
        # 添加一些预测数据
        for i in range(20):
            self.exit_system.analytics.record_prediction(
                prediction={"is_positive": i % 3 == 0, "confidence": 0.7 + i * 0.01},
                actual_outcome=i % 2 == 0
            )

        report = self.exit_system.generate_analytics_report()

        self.assertIn("report_period", report)
        self.assertIn("performance_summary", report)
        self.assertIn("signal_effectiveness", report)
        self.assertIn("recommendations", report)


# =============================================================================
# 性能测试
# =============================================================================

class TestPerformance(unittest.TestCase):
    """性能测试"""

    def test_high_frequency_data_processing(self):
        """测试高频数据处理能力"""
        collector = CapitalFlowCollector(max_history=10000)

        # 生成1000条高频数据
        base_time = datetime.now() - timedelta(hours=1)
        start_time = time.time()

        for i in range(1000):
            collector.add_trade(
                timestamp=base_time + timedelta(seconds=i),
                price=0.5 + random.uniform(-0.02, 0.02),
                size=random.uniform(1, 10),
                side="buy" if random.random() > 0.5 else "sell",
                trader_id=f"trader_{i % 100}"
            )

        add_time = time.time() - start_time

        # 查询指标
        start_time = time.time()
        metrics = collector.get_flow_metrics(window_seconds=60)
        query_time = time.time() - start_time

        print(f"\n性能测试结果:")
        print(f"  - 添加1000条数据耗时: {add_time:.3f}s")
        print(f"  - 查询指标耗时: {query_time:.3f}s")
        print(f"  - 数据队列大小: {len(collector._trades)}")

        # 性能断言
        self.assertLess(add_time, 1.0, "添加数据耗时过长")
        self.assertLess(query_time, 0.1, "查询耗时过长")


# =============================================================================
# 主入口
# =============================================================================

if __name__ == "__main__":
    import time

    print("=" * 70)
    print("资金流分析辅助决策系统 - 单元测试")
    print("=" * 70)

    # 运行所有测试
    unittest.main(verbosity=2)
