"""
买入策略单元测试

测试范围:
- 信号生成
- 入场条件验证
- 仓位大小计算
- 策略协调
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# 导入被测模块
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from strategy import (
    # 信号
    Signal,
    SignalType,
    SignalStrength,
    # 入场条件
    EntryConditionConfig,
    EntryCheckResult,
    # 仓位
    PositionSizerConfig,
    PositionSizingMethod,
    PortfolioState,
    # 执行
    ExecutionStrategyType,
    OrderType,
    OrderStatus,
    # 主策略
    BuyStrategy,
    BuyStrategyConfig,
)


class TestSignal:
    """测试信号类"""

    def test_signal_creation(self):
        """测试信号创建"""
        signal = Signal(
            type=SignalType.TECHNICAL_RSI_OVERSOLD,
            strength=SignalStrength.STRONG,
            confidence=0.85,
            market_id="test-market",
            timestamp=datetime.now(),
            description="RSI oversold signal",
        )

        assert signal.type == SignalType.TECHNICAL_RSI_OVERSOLD
        assert signal.strength == SignalStrength.STRONG
        assert signal.confidence == 0.85
        assert signal.score == 0.85 * 0.9  # confidence * strength value

    def test_signal_confidence_validation(self):
        """测试信号置信度验证"""
        with pytest.raises(ValueError):
            Signal(
                type=SignalType.TECHNICAL_MA_CROSS,
                strength=SignalStrength.MODERATE,
                confidence=1.5,  # 无效值
                market_id="test",
                timestamp=datetime.now(),
                description="Test",
            )


class TestEntryConditionConfig:
    """测试入场条件配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = EntryConditionConfig()

        assert config.price_min == 0.05
        assert config.price_max == 0.95
        assert config.death_zone_min == 0.60
        assert config.death_zone_max == 0.85
        assert config.allow_death_zone == False
        assert config.min_liquidity == 1000.0

    def test_custom_config(self):
        """测试自定义配置"""
        config = EntryConditionConfig(
            price_min=0.10,
            price_max=0.90,
            death_zone_min=0.55,
            death_zone_max=0.80,
            allow_death_zone=True,
            min_liquidity=2000.0,
        )

        assert config.price_min == 0.10
        assert config.allow_death_zone == True
        assert config.min_liquidity == 2000.0


class TestPositionSizerConfig:
    """测试仓位大小配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = PositionSizerConfig()

        assert config.default_method == PositionSizingMethod.FIXED_RISK
        assert config.fixed_risk_percentage == 0.02
        assert config.max_single_position_pct == 0.30
        assert config.max_total_exposure_pct == 0.80

    def test_kelly_config(self):
        """测试凯利公式配置"""
        config = PositionSizerConfig(
            default_method=PositionSizingMethod.KELLY_CRITERION,
            kelly_fraction=0.25,
        )

        assert config.default_method == PositionSizingMethod.KELLY_CRITERION
        assert config.kelly_fraction == 0.25


class TestPortfolioState:
    """测试投资组合状态"""

    def test_portfolio_creation(self):
        """测试投资组合创建"""
        portfolio = PortfolioState(
            total_capital=10000.0,
            available_capital=8000.0,
            total_risk_exposure=2000.0,
        )

        assert portfolio.total_capital == 10000.0
        assert portfolio.available_capital == 8000.0
        assert portfolio.used_capital == 2000.0
        assert portfolio.utilization_rate == 0.20

    def test_portfolio_with_positions(self):
        """测试带持仓的投资组合"""
        from strategy import Position

        position = Position(
            market_id="test-market",
            size=100.0,
            entry_price=50.0,
            entry_time=datetime.now(),
        )

        portfolio = PortfolioState(
            total_capital=10000.0,
            available_capital=5000.0,
            total_risk_exposure=2000.0,
            positions={"test-market": position},
        )

        assert len(portfolio.positions) == 1
        assert portfolio.positions["test-market"].size == 100.0


class TestBuyStrategyConfig:
    """测试买入策略配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = BuyStrategyConfig()

        assert config.min_signal_strength == SignalStrength.MODERATE
        assert config.min_signal_confidence == 0.6
        assert config.max_signals_per_market == 5
        assert config.default_execution_strategy == ExecutionStrategyType.IMMEDIATE
        assert config.dca_batches == 5
        assert config.max_daily_trades == 20

    def test_execution_strategy_config(self):
        """测试执行策略配置"""
        config = BuyStrategyConfig(
            default_execution_strategy=ExecutionStrategyType.TWAP,
            twap_slices=12,
            twap_duration_seconds=600,
        )

        assert config.default_execution_strategy == ExecutionStrategyType.TWAP
        assert config.twap_slices == 12
        assert config.twap_duration_seconds == 600


class TestBuyStrategy:
    """测试买入策略主类"""

    @pytest.fixture
    def mock_strategy(self):
        """创建模拟策略"""
        config = BuyStrategyConfig()
        strategy = BuyStrategy(config=config)

        # 设置投资组合
        strategy.set_portfolio(PortfolioState(
            total_capital=10000.0,
            available_capital=10000.0,
            total_risk_exposure=0.0,
        ))

        return strategy

    def test_strategy_initialization(self, mock_strategy):
        """测试策略初始化"""
        assert mock_strategy.state.is_active == False
        assert mock_strategy.portfolio.total_capital == 10000.0
        assert len(mock_strategy.trade_history) == 0

    def test_strategy_activation(self, mock_strategy):
        """测试策略激活"""
        mock_strategy.activate()
        assert mock_strategy.state.is_active == True

    def test_strategy_deactivation(self, mock_strategy):
        """测试策略停用"""
        mock_strategy.activate()
        mock_strategy.deactivate()
        assert mock_strategy.state.is_active == False

    def test_portfolio_update(self, mock_strategy):
        """测试投资组合更新"""
        mock_strategy.update_portfolio(
            total_capital=15000.0,
            available_capital=12000.0,
        )

        assert mock_strategy.portfolio.total_capital == 15000.0
        assert mock_strategy.portfolio.available_capital == 12000.0

    def test_stats(self, mock_strategy):
        """测试统计信息"""
        mock_strategy.activate()
        stats = mock_strategy.get_stats()

        assert "is_active" in stats
        assert "daily_trade_count" in stats
        assert "total_trades" in stats
        assert "portfolio" in stats
        assert stats["is_active"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
