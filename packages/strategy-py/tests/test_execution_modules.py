"""
交易执行模块单元测试

测试买入策略、执行引擎和信号评估器的功能。
"""

import asyncio
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

# 添加源目录到路径
sys.path.insert(0, "../src")

from strategy import (
    BuyStrategy,
    BuyStrategyConfig,
    BuyDecision,
    ExecutionEngine,
    ExecutionConfig,
    ExecutionReport,
    ExecutionResult,
    MarketCondition,
    Order,
    OrderStatus,
    OrderType,
    RiskLevel,
    Signal,
    SignalEvaluator,
    SignalMetrics,
    SignalQuality,
    SignalType,
    SignalWeights,
)


# =============================================================================
# 买入策略测试
# =============================================================================

class TestBuyStrategy(unittest.TestCase):
    """买入策略测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建模拟风险管理器
        self.mock_risk_manager = MagicMock()
        self.mock_risk_manager.check_death_zone = AsyncMock(return_value=False)
        self.mock_risk_manager.check_position_limits = AsyncMock(return_value=(True, "OK"))
        self.mock_risk_manager.get_total_exposure = AsyncMock(return_value=Decimal("1000"))
        self.mock_risk_manager.calculate_correlation_risk = AsyncMock(return_value=0.2)

        # 创建模拟信号生成器
        self.mock_signal_generator = MagicMock()
        self.mock_signal_generator.signal_type = SignalType.ODDS_BIAS
        self.mock_signal_generator.generate = AsyncMock(return_value=Signal(
            signal_type=SignalType.ODDS_BIAS,
            score=0.7,
            confidence=0.8,
        ))

        # 创建配置
        self.config = BuyStrategyConfig(
            min_composite_score=0.6,
            min_confidence=0.7,
            max_position_size_usd=Decimal("1000"),
            max_total_exposure_usd=Decimal("5000"),
        )

        # 创建策略
        self.strategy = BuyStrategy(
            signal_generators=[self.mock_signal_generator],
            risk_manager=self.mock_risk_manager,
            config=self.config,
        )

        # 创建市场条件
        self.market_condition = MarketCondition(
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

    def run_async(self, coro):
        """运行异步函数"""
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(len(self.strategy.signal_generators), 1)
        self.assertEqual(self.strategy.config.min_composite_score, 0.6)

    def test_evaluate_generates_signals(self):
        """测试评估生成信号"""
        decision = self.run_async(self.strategy.evaluate(self.market_condition))

        # 验证信号生成器被调用
        self.mock_signal_generator.generate.assert_called_once()

        # 验证返回决策
        self.assertIsInstance(decision, BuyDecision)
        self.assertEqual(decision.market_id, self.market_condition.market_id)

    def test_death_zone_check(self):
        """测试死亡区间检查"""
        # 设置死亡区间价格
        self.market_condition.current_price = Decimal("0.70")

        # 重新运行评估
        decision = self.run_async(self.strategy.evaluate(self.market_condition))

        # 应该因为死亡区间而拒绝
        self.assertFalse(decision.should_buy)
        self.assertIn("death zone", decision.decision_reason.lower())

    def test_composite_score_calculation(self):
        """测试综合评分计算"""
        # 创建多个信号
        signals = [
            Signal(signal_type=SignalType.ODDS_BIAS, score=0.8, confidence=0.9),
            Signal(signal_type=SignalType.TIME_DECAY, score=0.6, confidence=0.8),
        ]

        score = self.strategy._calculate_composite_score(signals)

        # 验证分数在合理范围内
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_position_size_calculation(self):
        """测试仓位大小计算"""
        composite_score = 0.8

        size = self.run_async(
            self.strategy._calculate_position_size(self.market_condition, composite_score)
        )

        # 验证仓位在合理范围内
        self.assertGreaterEqual(size, Decimal("0"))
        self.assertLessEqual(size, self.config.max_position_size_usd)


# =============================================================================
# 执行引擎测试
# =============================================================================

class TestExecutionEngine(unittest.TestCase):
    """执行引擎测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建模拟组件
        self.mock_order_manager = MagicMock()
        self.mock_risk_manager = MagicMock()
        self.mock_position_tracker = MagicMock()

        # 创建配置
        self.config = ExecutionConfig(
            dry_run=True,  # 使用模拟模式
            order_timeout_seconds=10,
        )

        # 创建引擎
        self.engine = ExecutionEngine(
            order_manager=self.mock_order_manager,
            risk_manager=self.mock_risk_manager,
            position_tracker=self.mock_position_tracker,
            config=self.config,
        )

        # 创建模拟决策
        self.mock_decision = MagicMock()
        self.mock_decision.market_id = "0x1234567890abcdef"
        self.mock_decision.should_buy = True
        self.mock_decision.side = "YES"
        self.mock_decision.size = Decimal("100")
        self.mock_decision.price = Decimal("0.35")
        self.mock_decision.order_type = "limit"
        self.mock_decision.confidence = 0.75
        self.mock_decision.composite_score = 0.68
        self.mock_decision.risk_level = RiskLevel.MEDIUM

    def run_async(self, coro):
        """运行异步函数"""
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.engine.config.dry_run, True)
        self.assertEqual(len(self.engine._execution_history), 0)

    def test_order_creation(self):
        """测试订单创建"""
        # 验证可以从决策创建订单
        order = Order(
            market_id=self.mock_decision.market_id,
            side=self.mock_decision.side,
            size=self.mock_decision.size,
            price=self.mock_decision.price,
            order_type=OrderType.LIMIT,
        )

        self.assertEqual(order.market_id, self.mock_decision.market_id)
        self.assertEqual(order.side, self.mock_decision.side)

    def test_execution_report_creation(self):
        """测试执行报告创建"""
        report = ExecutionReport(
            market_id="0x123",
            order_id="order-1",
            side="YES",
            requested_size=Decimal("100"),
            filled_size=Decimal("100"),
            avg_fill_price=Decimal("0.35"),
            status=OrderStatus.FILLED,
            result=ExecutionResult.SUCCESS,
            slippage_bps=50,
            execution_time_ms=1000,
        )

        self.assertEqual(report.result, ExecutionResult.SUCCESS)
        self.assertEqual(report.fill_percentage, 100.0)


# =============================================================================
# 信号评估器测试
# =============================================================================

class TestSignalEvaluator(unittest.TestCase):
    """信号评估器测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建内存数据库
        self.conn = sqlite3.connect(":memory:")

        # 创建评估器
        self.evaluator = SignalEvaluator(
            db_connection=self.conn,
            signal_sources=[],
            market_data_provider=None,
        )

    def tearDown(self):
        """清理测试环境"""
        self.conn.close()

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.evaluator.db_connection)
        self.assertIsNotNone(self.evaluator._metrics_cache)

    def test_record_signal(self):
        """测试记录信号"""
        record_id = self.evaluator.record_signal(
            signal_type="ODDS_BIAS",
            market_id="0x123",
            side="YES",
            confidence=0.8,
            score=0.7,
            predicted_outcome="YES",
            metadata={"source": "test"},
        )

        self.assertGreater(record_id, 0)

    def test_update_signal_result(self):
        """测试更新信号结果"""
        # 先记录信号
        record_id = self.evaluator.record_signal(
            signal_type="ODDS_BIAS",
            market_id="0x123",
            side="YES",
            confidence=0.8,
            score=0.7,
            predicted_outcome="YES",
        )

        # 更新结果
        success = self.evaluator.update_signal_result(
            record_id=record_id,
            actual_outcome="YES",
            pnl=Decimal("50"),
        )

        self.assertTrue(success)

    def test_signal_metrics_quality_score(self):
        """测试信号指标质量分数"""
        metrics = SignalMetrics(
            signal_type="TEST",
            accuracy=0.8,
            sharpe_ratio=1.5,
            win_rate=0.7,
            profit_factor=2.0,
            f1_score=0.75,
            max_drawdown=0.1,
            total_signals=100,
        )

        # 验证质量分数在合理范围内
        score = metrics.quality_score
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_signal_weights(self):
        """测试信号权重"""
        weights = SignalWeights()

        # 设置权重
        weights.set_weight("ODDS_BIAS", 0.3)
        weights.set_weight("TIME_DECAY", 0.2)
        weights.set_weight("ORDERBOOK_PRESSURE", 0.5)

        # 验证权重
        self.assertEqual(weights.get_weight("ODDS_BIAS"), 0.3)
        self.assertEqual(weights.get_weight("TIME_DECAY"), 0.2)

        # 归一化
        weights.normalize_weights()

        # 验证归一化后的权重总和为1
        total = sum(weights.weights.values())
        self.assertAlmostEqual(total, 1.0, places=5)


# =============================================================================
# 测试运行器
# =============================================================================

def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestBuyStrategy))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestSignalEvaluator))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
