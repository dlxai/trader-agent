"""
分层止盈服务测试
验证 PartialExitService 的核心逻辑
"""

import pytest
from datetime import datetime

from src.risk_management.partial_exit_service import (
    PartialExitService,
    PartialExitLevel,
    PartialExitSignal,
)


class TestPartialExitService:
    """分层止盈服务测试类"""

    def test_default_config(self):
        """测试默认配置是否正确"""
        service = PartialExitService()

        # 验证有3个档位
        assert len(service.levels) == 3

        # 验证每个档位的配置
        level_1 = service.levels[0]
        assert level_1.level == 1
        assert level_1.profit_level == 0.20  # 20%
        assert level_1.exit_ratio == 0.30  # 30%

        level_2 = service.levels[1]
        assert level_2.level == 2
        assert level_2.profit_level == 0.40  # 40%
        assert level_2.exit_ratio == 0.30  # 30%

        level_3 = service.levels[2]
        assert level_3.level == 3
        assert level_3.profit_level == 0.60  # 60%
        assert level_3.exit_ratio == 0.40  # 40%

    def test_check_level_1_triggered(self):
        """测试第1档止盈触发"""
        service = PartialExitService()

        # 当前利润 25%（超过 20%）
        signal = service.check("position_1", 0.25)

        # 验证信号
        assert signal is not None
        assert signal.position_id == "position_1"
        assert signal.level == 1
        assert signal.exit_ratio == 0.30
        assert signal.current_profit == 0.25
        assert signal.target_profit == 0.20
        assert signal.should_execute is True

    def test_check_level_2_triggered(self):
        """测试第2档止盈触发"""
        service = PartialExitService()

        # 先触发第1档
        service.check("position_1", 0.25)
        service.mark_level_executed("position_1", 1)

        # 当前利润 45%（超过 40%，第2档）
        signal = service.check("position_1", 0.45)

        # 验证第2档信号
        assert signal is not None
        assert signal.level == 2
        assert signal.exit_ratio == 0.30
        assert signal.target_profit == 0.40

    def test_check_no_trigger(self):
        """测试未触发止盈的情况"""
        service = PartialExitService()

        # 当前利润 10%（未达到 20%）
        signal = service.check("position_1", 0.10)

        # 验证未触发
        assert signal is None

    def test_mark_level_executed(self):
        """测试标记档位已执行"""
        service = PartialExitService()

        # 标记第1档已执行
        service.mark_level_executed("position_1", 1)

        # 验证状态
        executed = service._executed_levels.get("position_1", [])
        assert 1 in executed

        # 再次触发第1档应该不返回信号
        signal = service.check("position_1", 0.25)
        assert signal is None  # 第1档已执行，不再触发

    def test_get_position_status(self):
        """测试获取持仓状态"""
        service = PartialExitService()

        # 触发第1档并标记执行
        service.check("position_1", 0.25)
        service.mark_level_executed("position_1", 1)

        # 获取状态
        status = service.get_position_status("position_1")

        # 验证状态
        assert status["position_id"] == "position_1"
        assert status["total_levels"] == 3
        assert status["executed_levels"] == [1]
        assert status["remaining_levels"] == [2, 3]

    def test_custom_config(self):
        """测试自定义配置"""
        custom_config = [
            {
                "level": 1,
                "profit_level": 0.15,
                "exit_ratio": 0.50,
                "description": "Custom level 1",
            },
            {
                "level": 2,
                "profit_level": 0.30,
                "exit_ratio": 0.50,
                "description": "Custom level 2",
            },
        ]

        service = PartialExitService(custom_config=custom_config)

        # 验证自定义配置
        assert len(service.levels) == 2
        assert service.levels[0].profit_level == 0.15
        assert service.levels[0].exit_ratio == 0.50


class TestTrailingStopService:
    """移动止损服务测试类"""

    def test_default_config(self):
        """测试默认配置"""
        service = TrailingStopService()

        # 验证有6个档位
        assert len(service.levels) == 6

        # 验证第一个档位
        level_1 = service.levels[0]
        assert level_1.min_entry == 0.00
        assert level_1.max_entry == 0.30
        assert level_1.trigger_profit == 0.30
        assert level_1.drawdown == 0.15

    def test_initialize_position(self):
        """测试初始化持仓"""
        service = TrailingStopService()

        # 初始化持仓
        state = service.initialize_position("pos_1", 0.50, 0.50)

        # 验证状态
        assert state.position_id == "pos_1"
        assert state.highest_price == 0.50
        assert state.is_active is False
        assert state.trigger_profit == 0.40  # 对应 $0.30-0.60 档位
        assert state.drawdown == 0.12

    def test_trailing_stop_activation(self):
        """测试移动止损激活"""
        service = TrailingStopService()

        # 初始化持仓（入场价 $0.50）
        service.initialize_position("pos_1", 0.50, 0.50)

        # 价格上涨到 $0.70（利润 40%，达到触发条件）
        result = service.update_price("pos_1", 0.70)

        # 验证移动止损已激活
        state = service._states["pos_1"]
        assert state.is_active is True
        assert state.highest_price == 0.70
        # 止损价 = 最高价 * (1 - 回撤) = 0.70 * 0.88 = 0.616
        expected_stop = 0.70 * (1 - 0.12)
        assert abs(state.trailing_stop_price - expected_stop) < 0.001

        # 验证未触发退出（还在盈利）
        assert result is None

    def test_trailing_stop_trigger(self):
        """测试移动止损触发"""
        service = TrailingStopService()

        # 初始化并激活移动止损
        service.initialize_position("pos_1", 0.50, 0.50)
        service.update_price("pos_1", 0.70)  # 激活

        # 价格回撤到止损价以下
        state = service._states["pos_1"]
        trigger_price = state.trailing_stop_price * 0.99  # 略低于止损价

        result = service.update_price("pos_1", trigger_price)

        # 验证触发退出
        assert result is not None
        assert result["action"] == "exit"
        assert result["reason"] == "trailing_stop"
        assert result["current_price"] == trigger_price

    def test_no_trigger_below_activation(self):
        """测试激活前不触发"""
        service = TrailingStopService()

        # 初始化持仓
        service.initialize_position("pos_1", 0.50, 0.50)

        # 价格上涨但未达到触发利润（40%）
        # 从 $0.50 到 $0.60 = 20% 利润，未达到 40%
        result = service.update_price("pos_1", 0.60)

        # 验证未激活也未触发
        state = service._states["pos_1"]
        assert state.is_active is False
        assert result is None


class TestPriceProtection:
    """价格保护测试类"""

    def test_high_price_exit_triggered(self):
        """测试高价止盈触发"""
        from src.risk_management.price_protection import PriceProtection

        protection = PriceProtection(high_price_threshold=0.999)

        # 价格达到 0.999，触发高价止盈
        signal = protection.check_high_price_exit("pos_1", 0.999)

        assert signal is not None
        assert signal.should_exit is True
        assert signal.current_price == 0.999
        assert signal.threshold == 0.999

    def test_high_price_exit_not_triggered(self):
        """测试高价止盈未触发"""
        from src.risk_management.price_protection import PriceProtection

        protection = PriceProtection(high_price_threshold=0.999)

        # 价格 0.995，未达到 0.999
        signal = protection.check_high_price_exit("pos_1", 0.995)

        assert signal is None

    def test_token_confusion_detection(self):
        """测试 Token 混淆检测"""
        from src.risk_management.price_protection import TokenConfusionDetector

        detector = TokenConfusionDetector()

        # 模拟混淆情况：入场价 $0.50，新价格 $0.25
        # 价格变化 50%，且接近互补（0.50 + 0.25 = 0.75，接近 1.0）
        alert = detector.validate_price_update(
            position_id="pos_1",
            token_id="token_yes_123",
            entry_price=0.50,
            new_price=0.25,
        )

        # 验证检测到混淆
        assert alert is not None
        assert alert.position_id == "pos_1"
        assert alert.token_id == "token_yes_123"
        assert alert.detected_price == 0.25
        assert "VERIFY_TOKEN_ID" in alert.recommended_action
