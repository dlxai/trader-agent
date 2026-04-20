"""
固定止损服务测试
测试 FixedStopLossService 的核心功能
"""

import pytest
import sys
from pathlib import Path
from typing import List, Dict

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mock settings before importing the service
import types

# Create mock thresholds matching settings.py
MOCK_THRESHOLDS = [
    {"min": 0.00, "max": 0.20, "threshold": -0.30},
    {"min": 0.20, "max": 0.40, "threshold": -0.25},
    {"min": 0.40, "max": 0.60, "threshold": -0.20},
    {"min": 0.60, "max": 0.75, "threshold": -0.15},
    {"min": 0.75, "max": 0.85, "threshold": -0.12},
    {"min": 0.85, "max": 0.90, "threshold": -0.10},
    {"min": 0.90, "max": 0.95, "threshold": -0.05},
    {"min": 0.95, "max": 0.97, "threshold": -0.04},
    {"min": 0.97, "max": 0.99, "threshold": -0.03},
    {"min": 0.99, "max": 1.00, "threshold": -0.02},
]

# Create mock StopLossConfig
class MockStopLossConfig:
    fixed_thresholds = MOCK_THRESHOLDS
    fixed_stop_enabled = True

class MockSettings:
    stop_loss = MockStopLossConfig()

# Create and register mock module
mock_settings_module = types.ModuleType('config.settings')
mock_settings_module.settings = MockSettings()
sys.modules['config.settings'] = mock_settings_module
sys.modules['settings'] = mock_settings_module

# Now we can import the service
from risk_management.fixed_stop_service import (
    FixedStopLossService,
    StopLossLevel,
    StopLossSignal,
)


class TestFixedStopLossServiceInit:
    """测试初始化功能"""

    def test_default_initialization(self):
        """测试默认初始化"""
        service = FixedStopLossService()

        assert service is not None
        assert len(service.levels) == 10  # 10档阈值
        assert service._check_count == 0
        assert service._trigger_count == 0

    def test_custom_thresholds(self):
        """测试自定义阈值配置"""
        custom_thresholds: List[Dict] = [
            {"min": 0.00, "max": 0.50, "threshold": -0.20},
            {"min": 0.50, "max": 1.00, "threshold": -0.10},
        ]

        service = FixedStopLossService(thresholds=custom_thresholds)

        assert len(service.levels) == 2
        assert service.levels[0].min_price == 0.00
        assert service.levels[0].max_price == 0.50
        assert service.levels[0].threshold == -0.20


class TestStopLossThresholds:
    """测试各档位止损阈值计算"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_extreme_low_price_stop_loss(self, service):
        """测试极低价区止损阈值 (-30%)"""
        threshold = service.get_stop_loss_threshold(0.10)
        assert threshold == -0.30

        threshold = service.get_stop_loss_threshold(0.15)
        assert threshold == -0.30

    def test_low_price_stop_loss(self, service):
        """测试低价区止损阈值 (-25%)"""
        threshold = service.get_stop_loss_threshold(0.25)
        assert threshold == -0.25

        threshold = service.get_stop_loss_threshold(0.35)
        assert threshold == -0.25

    def test_mid_low_price_stop_loss(self, service):
        """测试中低价区止损阈值 (-20%)"""
        threshold = service.get_stop_loss_threshold(0.45)
        assert threshold == -0.20

        threshold = service.get_stop_loss_threshold(0.55)
        assert threshold == -0.20

    def test_mid_price_stop_loss(self, service):
        """测试中价区止损阈值 (-15%)"""
        threshold = service.get_stop_loss_threshold(0.65)
        assert threshold == -0.15

        threshold = service.get_stop_loss_threshold(0.70)
        assert threshold == -0.15

    def test_mid_high_price_stop_loss(self, service):
        """测试中高价区止损阈值 (-12%)"""
        threshold = service.get_stop_loss_threshold(0.78)
        assert threshold == -0.12

        threshold = service.get_stop_loss_threshold(0.82)
        assert threshold == -0.12

    def test_high_price_stop_loss(self, service):
        """测试高价区止损阈值 (-10%)"""
        threshold = service.get_stop_loss_threshold(0.86)
        assert threshold == -0.10

        threshold = service.get_stop_loss_threshold(0.88)
        assert threshold == -0.10

    def test_near_end_price_stop_loss(self, service):
        """测试准扫尾盘区止损阈值 (-5%)"""
        threshold = service.get_stop_loss_threshold(0.92)
        assert threshold == -0.05

    def test_end_low_price_stop_loss(self, service):
        """测试扫尾盘低档区止损阈值 (-4%)"""
        threshold = service.get_stop_loss_threshold(0.96)
        assert threshold == -0.04

    def test_end_mid_price_stop_loss(self, service):
        """测试扫尾盘中档区止损阈值 (-3%)"""
        threshold = service.get_stop_loss_threshold(0.98)
        assert threshold == -0.03

    def test_end_high_price_stop_loss(self, service):
        """测试扫尾盘高档区止损阈值 (-2%)"""
        threshold = service.get_stop_loss_threshold(0.995)
        assert threshold == -0.02


class TestStopLossTrigger:
    """测试止损触发逻辑"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_no_trigger_when_price_above_threshold(self, service):
        """测试价格高于止损阈值时不触发"""
        # 入场价 $0.50，阈值 -20%，当前价 $0.45（亏损 10%，未达到 -20%）
        signal = service.check_stop_loss("pos_001", 0.50, 0.45)

        assert signal is None
        assert service._check_count == 1
        assert service._trigger_count == 0

    def test_trigger_when_price_below_threshold(self, service):
        """测试价格低于止损阈值时触发"""
        # 入场价 $0.50，阈值 -20%，当前价 $0.38（亏损 24%，超过 -20%）
        signal = service.check_stop_loss("pos_002", 0.50, 0.38)

        assert signal is not None
        assert isinstance(signal, StopLossSignal)
        assert signal.position_id == "pos_002"
        assert signal.trigger_type == "fixed_stop_loss"
        assert signal.threshold == -0.20
        assert abs(signal.profit_pct - (-0.24)) < 0.01  # 约 -24%
        assert signal.should_exit is True
        assert signal.exit_ratio == 1.0

        assert service._check_count == 1
        assert service._trigger_count == 1

    def test_exact_threshold_trigger(self, service):
        """测试刚好达到止损阈值时触发"""
        # 入场价 $0.80，阈值 -12%，当前价 $0.704（刚好亏损 12%）
        signal = service.check_stop_loss("pos_003", 0.80, 0.704)

        assert signal is not None
        assert signal.threshold == -0.12

    def test_boundary_price_at_level_edge(self, service):
        """测试刚好在档位边界的价格"""
        # 入场价刚好是 $0.20，应该使用 $0.20-$0.40 档位（-25%）
        threshold = service.get_stop_loss_threshold(0.20)
        assert threshold == -0.25

        # 入场价刚好是 $0.40，应该使用 $0.40-$0.60 档位（-20%）
        threshold = service.get_stop_loss_threshold(0.40)
        assert threshold == -0.20

    def test_multiple_checks_same_position(self, service):
        """测试同一持仓多次检查"""
        # 第一次检查：未达到止损
        signal1 = service.check_stop_loss("pos_004", 0.60, 0.55)
        assert signal1 is None

        # 第二次检查：达到止损
        signal2 = service.check_stop_loss("pos_004", 0.60, 0.45)
        assert signal2 is not None

        assert service._check_count == 2
        assert service._trigger_count == 1


class TestStopLossLevelRetrieval:
    """测试止损档位获取"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_get_stop_loss_level_valid_prices(self, service):
        """测试获取有效价格的止损档位"""
        level = service.get_stop_loss_level(0.30)

        assert level is not None
        assert level.min_price == 0.20
        assert level.max_price == 0.40
        assert level.threshold == -0.25

    def test_get_stop_loss_level_invalid_price_negative(self, service):
        """测试获取负价格的止损档位"""
        level = service.get_stop_loss_level(-0.10)
        assert level is None

    def test_get_stop_loss_level_invalid_price_over_one(self, service):
        """测试获取超过1.0的价格的止损档位"""
        level = service.get_stop_loss_level(1.50)
        assert level is None

    def test_get_stop_loss_level_at_one(self, service):
        """测试价格为1.0时的止损档位"""
        level = service.get_stop_loss_level(1.0)

        # 应该返回最后一档
        assert level is not None
        assert level.min_price == 0.99
        assert level.max_price == 1.00
        assert level.threshold == -0.02


class TestProfitCalculation:
    """测试盈亏百分比计算"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_calculate_profit_positive(self, service):
        """测试正收益计算"""
        profit = service.calculate_profit_pct(0.50, 0.60)
        assert abs(profit - 0.20) < 0.001  # 20% 收益

    def test_calculate_profit_negative(self, service):
        """测试亏损计算"""
        profit = service.calculate_profit_pct(0.50, 0.40)
        assert abs(profit - (-0.20)) < 0.001  # -20% 亏损

    def test_calculate_profit_zero(self, service):
        """测试零收益"""
        profit = service.calculate_profit_pct(0.50, 0.50)
        assert abs(profit - 0.0) < 0.001  # 0% 收益

    def test_calculate_profit_invalid_entry(self, service):
        """测试无效入场价"""
        profit = service.calculate_profit_pct(0.0, 0.50)
        assert profit == 0.0

        profit = service.calculate_profit_pct(-0.10, 0.50)
        assert profit == 0.0


class TestValidationAndStats:
    """测试验证和统计功能"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_validate_thresholds_valid(self, service):
        """测试验证有效的阈值配置"""
        assert service.validate_thresholds() is True

    def test_validate_thresholds_empty(self):
        """测试验证空的阈值配置"""
        service = FixedStopLossService(thresholds=[])
        assert service.validate_thresholds() is False

    def test_validate_thresholds_invalid_positive(self):
        """测试验证正阈值（无效）"""
        invalid_thresholds = [
            {"min": 0.00, "max": 1.00, "threshold": 0.10},  # 正阈值（无效）
        ]
        service = FixedStopLossService(thresholds=invalid_thresholds)
        assert service.validate_thresholds() is False

    def test_get_stats_initial(self, service):
        """测试获取初始统计信息"""
        stats = service.get_stats()

        assert stats["enabled"] is True
        assert stats["total_levels"] == 10
        assert stats["check_count"] == 0
        assert stats["trigger_count"] == 0
        assert stats["trigger_rate"] == 0.0
        assert len(stats["levels_config"]) == 10

    def test_get_stats_after_checks(self, service):
        """测试检查后的统计信息"""
        # 执行一些检查
        service.check_stop_loss("pos_1", 0.50, 0.48)  # 未触发
        service.check_stop_loss("pos_2", 0.50, 0.35)  # 触发

        stats = service.get_stats()

        assert stats["check_count"] == 2
        assert stats["trigger_count"] == 1
        assert stats["trigger_rate"] == 0.5


class TestEdgeCases:
    """测试边界情况"""

    @pytest.fixture
    def service(self):
        return FixedStopLossService()

    def test_very_small_price_drop(self, service):
        """测试微小跌幅"""
        # 入场价 $0.50，当前价 $0.499，跌幅 0.2%
        signal = service.check_stop_loss("pos_001", 0.50, 0.499)
        assert signal is None  # 不应触发

    def test_boundary_between_levels(self, service):
        """测试档位边界"""
        # 在 $0.20 边界，应该使用 $0.20-$0.40 档位（-25%）
        threshold = service.get_stop_loss_threshold(0.20)
        assert threshold == -0.25

        # 略低于 $0.20，应该使用 $0.00-$0.20 档位（-30%）
        threshold = service.get_stop_loss_threshold(0.199)
        assert threshold == -0.30

    def test_zero_price(self, service):
        """测试零价格"""
        level = service.get_stop_loss_level(0.0)
        assert level is not None
        assert level.min_price == 0.00
        assert level.max_price == 0.20

    def test_price_exactly_at_max(self, service):
        """测试价格刚好在档位上限"""
        # $0.20 应该属于 $0.20-$0.40 档位
        level = service.get_stop_loss_level(0.20)
        assert level.min_price == 0.20

    def test_rapid_price_movement(self, service):
        """测试价格快速变动"""
        position_id = "rapid_test"
        entry_price = 0.50

        # 价格快速下跌
        prices = [0.50, 0.48, 0.45, 0.40, 0.38]
        signals = []

        for price in prices:
            signal = service.check_stop_loss(position_id, entry_price, price)
            if signal:
                signals.append(signal)

        # 应该只触发一次止损
        assert len(signals) == 1
        assert signals[0].profit_pct < -0.20  # 超过 -20% 阈值


class TestIntegration:
    """集成测试"""

    def test_full_workflow_low_price(self):
        """测试低价区完整流程"""
        service = FixedStopLossService()

        # 低价入场 $0.15，阈值 -30%
        entry_price = 0.15
        threshold = service.get_stop_loss_threshold(entry_price)
        assert threshold == -0.30

        # 价格下跌到 $0.10，亏损 33.3%，应该触发止损
        signal = service.check_stop_loss("low_price_pos", entry_price, 0.10)

        assert signal is not None
        assert signal.threshold == -0.30
        assert signal.profit_pct < -0.30
        assert signal.should_exit is True

    def test_full_workflow_high_price(self):
        """测试高价区完整流程"""
        service = FixedStopLossService()

        # 高价入场 $0.90，阈值 -10%
        entry_price = 0.90
        threshold = service.get_stop_loss_threshold(entry_price)
        assert threshold == -0.10

        # 价格下跌到 $0.80，亏损 11.1%，应该触发止损
        signal = service.check_stop_loss("high_price_pos", entry_price, 0.80)

        assert signal is not None
        assert signal.threshold == -0.10
        assert signal.profit_pct < -0.10

    def test_no_trigger_when_profit_positive(self):
        """测试盈利时不触发止损"""
        service = FixedStopLossService()

        # 入场 $0.50，当前 $0.60（盈利 20%）
        signal = service.check_stop_loss("profit_pos", 0.50, 0.60)

        assert signal is None

    def test_all_levels_integration(self):
        """测试所有档位的集成"""
        service = FixedStopLossService()

        # 测试价格点
        test_prices = [0.10, 0.30, 0.50, 0.70, 0.80, 0.88, 0.92, 0.96, 0.98, 0.995]

        for price in test_prices:
            threshold = service.get_stop_loss_threshold(price)
            level = service.get_stop_loss_level(price)

            assert level is not None, f"No level found for price {price}"
            assert threshold < 0, f"Threshold should be negative for price {price}"
            assert level.min_price <= price <= level.max_price or (price == 1.0 and level.max_price == 1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
