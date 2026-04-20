"""
仓位大小计算模块 (Position Sizer)

根据多种策略计算合适的仓位大小：
- 凯利公式（Kelly Criterion）
- 固定风险比例（如总资金 2%）
- 信心度加权（信号强度 → 仓位大小）
- 最大仓位限制（单市场、总体）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union
import math
import logging


logger = logging.getLogger(__name__)


class PositionSizingMethod(Enum):
    """仓位大小计算方法"""
    KELLY_CRITERION = auto()       # 凯利公式
    FIXED_RISK = auto()            # 固定风险比例
    CONFIDENCE_WEIGHTED = auto()   # 信心度加权
    EQUAL_WEIGHT = auto()          # 等权重
    VOLATILITY_ADJUSTED = auto()   # 波动率调整


@dataclass
class PortfolioState:
    """投资组合状态"""
    total_capital: float                    # 总资金
    available_capital: float                # 可用资金
    total_risk_exposure: float              # 总风险敞口
    positions: Dict[str, 'Position'] = field(default_factory=dict)  # 当前持仓

    @property
    def used_capital(self) -> float:
        """已使用资金"""
        return self.total_capital - self.available_capital

    @property
    def utilization_rate(self) -> float:
        """资金利用率"""
        return self.used_capital / self.total_capital if self.total_capital > 0 else 0


@dataclass
class Position:
    """持仓信息"""
    market_id: str
    size: float                 # 仓位大小
    entry_price: float          # 入场价格
    entry_time: datetime
    stop_loss: Optional[float] = None  # 止损价格
    take_profit: Optional[float] = None  # 止盈价格
    risk_amount: float = 0.0    # 风险金额


@dataclass
class SizingRecommendation:
    """仓位大小建议"""
    method: PositionSizingMethod
    recommended_size: float           # 建议仓位大小
    recommended_risk_amount: float      # 建议风险金额
    confidence: float                  # 建议置信度 (0-1)
    reasoning: str                     # 建议理由
    constraints_applied: List[str] = field(default_factory=list)  # 应用的限制

    @property
    def percentage_of_capital(self) -> float:
        """占总资金百分比"""
        # 这里会在后面通过 portfolio 计算
        return 0.0


@dataclass
class PositionSizingResult:
    """仓位大小计算结果"""
    market_id: str
    final_size: float                   # 最终仓位大小
    final_risk_amount: float            # 最终风险金额
    method_used: PositionSizingMethod   # 使用的方法
    sizing_recommendations: List[SizingRecommendation] = field(default_factory=list)
    applied_constraints: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def risk_percentage(self) -> float:
        """风险百分比"""
        return self.final_risk_amount / self.final_size if self.final_size > 0 else 0


# ==================== 仓位大小计算策略 ====================

class SizingStrategy(ABC):
    """仓位大小计算策略基类"""

    def __init__(self, method: PositionSizingMethod):
        self.method = method

    @abstractmethod
    def calculate(
        self,
        market_id: str,
        signals: List[Dict[str, Any]],
        portfolio: PortfolioState,
        entry_price: float,
        stop_loss: Optional[float] = None,
        **kwargs
    ) -> SizingRecommendation:
        """计算仓位大小"""
        pass


class KellyCriterionStrategy(SizingStrategy):
    """
    凯利公式策略

    f* = (bp - q) / b

    其中：
    - f*: 最优资金比例
    - b: 赔率（平均盈利/平均亏损）
    - p: 胜率
    - q: 败率 (1-p)
    """

    def __init__(
        self,
        kelly_fraction: float = 0.25,  # 使用 1/4 凯利（保守）
        min_edge: float = 0.02,         # 最小优势
        max_position_size: float = 0.25,  # 最大仓位限制
    ):
        super().__init__(PositionSizingMethod.KELLY_CRITERION)
        self.kelly_fraction = kelly_fraction
        self.min_edge = min_edge
        self.max_position_size = max_position_size

    def calculate(
        self,
        market_id: str,
        signals: List[Dict[str, Any]],
        portfolio: PortfolioState,
        entry_price: float,
        stop_loss: Optional[float] = None,
        win_rate: float = 0.55,
        avg_win: float = 1.0,
        avg_loss: float = 0.5,
        **kwargs
    ) -> SizingRecommendation:
        """使用凯利公式计算仓位"""

        # 计算赔率
        b = avg_win / avg_loss if avg_loss > 0 else 2.0
        p = win_rate
        q = 1 - p

        # 凯利公式: f* = (bp - q) / b
        kelly_fraction_raw = (b * p - q) / b if b > 0 else 0

        # 应用保守系数
        kelly_fraction = kelly_fraction_raw * self.kelly_fraction

        # 确保非负
        kelly_fraction = max(0, kelly_fraction)

        # 应用最大仓位限制
        kelly_fraction = min(kelly_fraction, self.max_position_size)

        # 计算仓位大小
        position_size = portfolio.total_capital * kelly_fraction

        # 计算风险金额
        risk_per_share = entry_price - stop_loss if stop_loss and entry_price > stop_loss else entry_price * 0.05
        risk_amount = position_size * (risk_per_share / entry_price) if entry_price > 0 else 0

        # 确定置信度
        if kelly_fraction_raw < 0:
            confidence = 0.3
            reasoning = f"Negative Kelly fraction ({kelly_fraction_raw:.3f}) indicates no edge"
        elif kelly_fraction_raw < self.min_edge:
            confidence = 0.5
            reasoning = f"Small Kelly fraction ({kelly_fraction_raw:.3f}) indicates weak edge"
        else:
            confidence = min(0.9, 0.6 + kelly_fraction_raw)
            reasoning = f"Kelly fraction {kelly_fraction_raw:.3f} indicates good edge (b={b:.2f}, p={p:.2f})"

        return SizingRecommendation(
            method=self.method,
            recommended_size=position_size,
            recommended_risk_amount=risk_amount,
            confidence=confidence,
            reasoning=reasoning,
            constraints_applied=[
                f"Kelly fraction: {self.kelly_fraction}",
                f"Max position: {self.max_position_size:.1%}",
            ] if self.kelly_fraction < 1.0 or self.max_position_size < 1.0 else [],
        )


class FixedRiskStrategy(SizingStrategy):
    """
    固定风险比例策略

    每笔交易风险固定的资金比例
    仓位大小 = 风险资金 / 每股风险
    """

    def __init__(
        self,
        risk_percentage: float = 0.02,  # 默认2%风险
        max_position_percentage: float = 0.25,  # 最大仓位25%
        min_position_size: float = 10.0,  # 最小仓位
    ):
        super().__init__(PositionSizingMethod.FIXED_RISK)
        self.risk_percentage = risk_percentage
        self.max_position_percentage = max_position_percentage
        self.min_position_size = min_position_size

    def calculate(
        self,
        market_id: str,
        signals: List[Dict[str, Any]],
        portfolio: PortfolioState,
        entry_price: float,
        stop_loss: Optional[float] = None,
        **kwargs
    ) -> SizingRecommendation:
        """使用固定风险比例计算仓位"""

        # 计算风险资金
        risk_amount = portfolio.total_capital * self.risk_percentage

        # 计算每股风险
        if stop_loss and entry_price > stop_loss:
            risk_per_share = entry_price - stop_loss
        else:
            # 如果没有止损，使用默认5%止损
            risk_per_share = entry_price * 0.05

        # 计算仓位大小
        if risk_per_share > 0 and entry_price > 0:
            position_size_shares = risk_amount / risk_per_share
            position_size = position_size_shares * entry_price
        else:
            position_size = 0

        # 应用限制
        constraints = []

        # 最大仓位限制
        max_position = portfolio.total_capital * self.max_position_percentage
        if position_size > max_position:
            position_size = max_position
            constraints.append(f"Max position cap: {self.max_position_percentage:.1%}")

        # 最小仓位限制
        if position_size < self.min_position_size and position_size > 0:
            position_size = 0
            constraints.append(f"Min position size: ${self.min_position_size:.2f}")

        # 可用资金限制
        if position_size > portfolio.available_capital:
            position_size = portfolio.available_capital
            constraints.append(f"Available capital limit")

        # 重新计算风险金额（基于实际仓位）
        if entry_price > 0:
            actual_risk_amount = position_size * (risk_per_share / entry_price)
        else:
            actual_risk_amount = 0

        # 确定置信度 (信号字典格式: {"score": float, "strength": int, "confidence": float})
        if len(signals) == 0:
            confidence = 0.5
        else:
            avg_signal_score = sum(s.get("score", 0.5) for s in signals) / len(signals)
            confidence = min(0.9, 0.5 + avg_signal_score * 0.4)

        reasoning = (
            f"Fixed risk strategy: {self.risk_percentage:.1%} risk (${risk_amount:,.2f}), "
            f"risk per share: ${risk_per_share:.4f}, position: ${position_size:,.2f}"
        )

        return SizingRecommendation(
            method=self.method,
            recommended_size=position_size,
            recommended_risk_amount=actual_risk_amount,
            confidence=confidence,
            reasoning=reasoning,
            constraints_applied=constraints,
        )


class ConfidenceWeightedStrategy(SizingStrategy):
    """
    信心度加权策略

    根据信号强度调整仓位大小
    仓位大小 = 基础仓位 × 信号强度加权
    """

    def __init__(
        self,
        base_position_percentage: float = 0.10,  # 基础仓位 10%
        min_position_percentage: float = 0.02,  # 最小仓位 2%
        max_position_percentage: float = 0.30,  # 最大仓位 30%
        confidence_scaling: float = 1.5,  # 信心度缩放因子
    ):
        super().__init__(PositionSizingMethod.CONFIDENCE_WEIGHTED)
        self.base_position_percentage = base_position_percentage
        self.min_position_percentage = min_position_percentage
        self.max_position_percentage = max_position_percentage
        self.confidence_scaling = confidence_scaling

    def calculate(
        self,
        market_id: str,
        signals: List[Dict[str, Any]],
        portfolio: PortfolioState,
        entry_price: float,
        stop_loss: Optional[float] = None,
        **kwargs
    ) -> SizingRecommendation:
        """使用信心度加权计算仓位"""

        if not signals:
            # 没有信号，使用最小仓位
            position_size = portfolio.total_capital * self.min_position_percentage

            return SizingRecommendation(
                method=self.method,
                recommended_size=position_size,
                recommended_risk_amount=position_size * 0.05,  # 假设5%风险
                confidence=0.3,
                reasoning="No signals available, using minimum position size",
                constraints_applied=["No signals"],
            )

        # 计算加权信号强度 (信号字典格式: {"score": float, "strength": int, "confidence": float})
        total_weight = 0
        weighted_score = 0

        for signal in signals:
            # 信号强度权重 (strength: 1=LOW, 2=MEDIUM, 3=HIGH)
            weight = signal.get("strength", 2) * signal.get("confidence", 0.5)
            total_weight += weight
            weighted_score += signal.get("score", 0.5) * weight

        # 归一化平均分数
        if total_weight > 0:
            avg_signal_score = weighted_score / total_weight
        else:
            avg_signal_score = 0

        # 计算信心度调整系数
        confidence_factor = 1 + (avg_signal_score - 0.5) * self.confidence_scaling
        confidence_factor = max(0.5, min(2.0, confidence_factor))  # 限制在 0.5-2.0

        # 计算基础仓位
        base_position = portfolio.total_capital * self.base_position_percentage

        # 应用信心度调整
        adjusted_position = base_position * confidence_factor

        # 应用限制
        constraints = []

        # 最小仓位限制
        min_position = portfolio.total_capital * self.min_position_percentage
        if adjusted_position < min_position:
            adjusted_position = 0
            constraints.append(f"Below minimum position {self.min_position_percentage:.1%}")

        # 最大仓位限制
        max_position = portfolio.total_capital * self.max_position_percentage
        if adjusted_position > max_position:
            adjusted_position = max_position
            constraints.append(f"Capped at maximum {self.max_position_percentage:.1%}")

        # 可用资金限制
        if adjusted_position > portfolio.available_capital:
            adjusted_position = portfolio.available_capital
            constraints.append("Limited by available capital")

        # 计算风险金额
        if stop_loss and entry_price > stop_loss:
            risk_per_share = entry_price - stop_loss
            risk_amount = adjusted_position * (risk_per_share / entry_price) if entry_price > 0 else 0
        else:
            # 默认5%风险
            risk_amount = adjusted_position * 0.05

        # 计算置信度
        confidence = min(0.95, 0.4 + avg_signal_score * 0.5)

        reasoning = (
            f"Confidence-weighted sizing: base={self.base_position_percentage:.1%}, "
            f"signal_score={avg_signal_score:.2f}, confidence_factor={confidence_factor:.2f}, "
            f"final_size=${adjusted_position:,.2f}"
        )

        return SizingRecommendation(
            method=self.method,
            recommended_size=adjusted_position,
            recommended_risk_amount=risk_amount,
            confidence=confidence,
            reasoning=reasoning,
            constraints_applied=constraints if constraints else [],
        )


# ==================== 仓位大小计算器 ====================

@dataclass
class PositionSizerConfig:
    """仓位大小计算器配置"""
    # 默认方法
    default_method: PositionSizingMethod = PositionSizingMethod.FIXED_RISK

    # 凯利公式参数
    kelly_fraction: float = 0.25

    # 固定风险参数
    fixed_risk_percentage: float = 0.02

    # 信心度加权参数
    base_position_pct: float = 0.10
    min_position_pct: float = 0.02
    max_position_pct: float = 0.30

    # 全局限制
    max_single_position_pct: float = 0.30      # 单市场最大仓位
    max_total_exposure_pct: float = 0.80       # 总敞口上限
    min_trade_size: float = 10.0               # 最小交易金额

    # 多方法组合
    enable_multiple_methods: bool = True       # 启用多方法计算
    combine_method: str = "weighted_average"     # 组合方法


class PositionSizer:
    """仓位大小计算器"""

    def __init__(
        self,
        config: Optional[PositionSizerConfig] = None,
        kelly_strategy: Optional[KellyCriterionStrategy] = None,
        fixed_risk_strategy: Optional[FixedRiskStrategy] = None,
        confidence_strategy: Optional[ConfidenceWeightedStrategy] = None,
    ):
        self.config = config or PositionSizerConfig()

        # 初始化策略
        self._kelly_strategy = kelly_strategy or KellyCriterionStrategy(
            kelly_fraction=self.config.kelly_fraction,
        )
        self._fixed_risk_strategy = fixed_risk_strategy or FixedRiskStrategy(
            risk_percentage=self.config.fixed_risk_percentage,
            max_position_percentage=self.config.max_single_position_pct,
        )
        self._confidence_strategy = confidence_strategy or ConfidenceWeightedStrategy(
            base_position_percentage=self.config.base_position_pct,
            min_position_percentage=self.config.min_position_pct,
            max_position_percentage=self.config.max_single_position_pct,
        )

    def calculate_position_size(
        self,
        market_id: str,
        portfolio: PortfolioState,
        entry_price: float,
        signals: List[Dict[str, Any]],
        stop_loss: Optional[float] = None,
        method: Optional[PositionSizingMethod] = None,
        **kwargs
    ) -> PositionSizingResult:
        """
        计算仓位大小

        Args:
            market_id: 市场ID
            portfolio: 投资组合状态
            entry_price: 入场价格
            signals: 交易信号列表
            stop_loss: 止损价格（可选）
            method: 计算方法（可选，默认使用配置的方法）
            **kwargs: 其他参数

        Returns:
            PositionSizingResult: 仓位大小计算结果
        """
        # 确定使用的方法
        if method is None:
            method = self.config.default_method

        recommendations: List[SizingRecommendation] = []

        try:
            # 根据配置计算一个或多个方法的推荐
            if self.config.enable_multiple_methods:
                # 计算所有方法的推荐
                recommendations.append(
                    self._kelly_strategy.calculate(
                        market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                    )
                )
                recommendations.append(
                    self._fixed_risk_strategy.calculate(
                        market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                    )
                )
                recommendations.append(
                    self._confidence_strategy.calculate(
                        market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                    )
                )
            else:
                # 只计算指定方法
                if method == PositionSizingMethod.KELLY_CRITERION:
                    recommendations.append(
                        self._kelly_strategy.calculate(
                            market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                        )
                    )
                elif method == PositionSizingMethod.FIXED_RISK:
                    recommendations.append(
                        self._fixed_risk_strategy.calculate(
                            market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                        )
                    )
                elif method == PositionSizingMethod.CONFIDENCE_WEIGHTED:
                    recommendations.append(
                        self._confidence_strategy.calculate(
                            market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                        )
                    )
                else:
                    # 默认使用固定风险
                    recommendations.append(
                        self._fixed_risk_strategy.calculate(
                            market_id, signals, portfolio, entry_price, stop_loss, **kwargs
                        )
                    )

        except Exception as e:
            logger.error(f"Error calculating position size for {market_id}: {e}", exc_info=True)
            # 返回一个保守的默认推荐
            recommendations.append(SizingRecommendation(
                method=PositionSizingMethod.FIXED_RISK,
                recommended_size=portfolio.total_capital * 0.02,
                recommended_risk_amount=portfolio.total_capital * 0.02 * 0.05,
                confidence=0.3,
                reasoning=f"Error in calculation, using conservative default: {str(e)}",
                constraints_applied=["error_fallback"],
            ))

        # 组合多个推荐（如果启用）
        final_recommendation = self._combine_recommendations(
            recommendations, self.config.combine_method
        )

        # 应用全局约束
        final_size, applied_constraints = self._apply_global_constraints(
            final_recommendation.recommended_size,
            market_id,
            portfolio,
            entry_price,
        )

        # 计算最终风险金额
        if stop_loss and entry_price > stop_loss:
            risk_per_share = entry_price - stop_loss
            final_risk_amount = final_size * (risk_per_share / entry_price) if entry_price > 0 else 0
        else:
            # 使用推荐的风险金额比例
            risk_ratio = final_recommendation.recommended_risk_amount / final_recommendation.recommended_size if final_recommendation.recommended_size > 0 else 0.05
            final_risk_amount = final_size * risk_ratio

        return PositionSizingResult(
            market_id=market_id,
            final_size=final_size,
            final_risk_amount=final_risk_amount,
            method_used=final_recommendation.method,
            sizing_recommendations=recommendations,
            applied_constraints={
                "global_constraints": applied_constraints,
                "method": self.config.combine_method,
            },
            timestamp=datetime.now(),
        )

    def _combine_recommendations(
        self,
        recommendations: List[SizingRecommendation],
        method: str = "weighted_average"
    ) -> SizingRecommendation:
        """组合多个推荐"""
        if not recommendations:
            raise ValueError("No recommendations to combine")

        if len(recommendations) == 1:
            return recommendations[0]

        if method == "weighted_average":
            # 按置信度加权平均
            total_weight = sum(r.confidence for r in recommendations)
            if total_weight == 0:
                total_weight = len(recommendations)
                weights = [1.0 / len(recommendations)] * len(recommendations)
            else:
                weights = [r.confidence / total_weight for r in recommendations]

            # 加权平均仓位大小
            combined_size = sum(
                r.recommended_size * w for r, w in zip(recommendations, weights)
            )
            combined_risk = sum(
                r.recommended_risk_amount * w for r, w in zip(recommendations, weights)
            )
            combined_confidence = sum(
                r.confidence * w for r, w in zip(recommendations, weights)
            )

            # 选择主方法（置信度最高的）
            primary_method = max(recommendations, key=lambda r: r.confidence).method

            # 合并限制条件
            all_constraints = []
            for r in recommendations:
                all_constraints.extend(r.constraints_applied)

            # 合并理由
            reasoning = "Combined recommendation using weighted average:\n" + "\n".join(
                f"  - {r.method.name}: ${r.recommended_size:,.2f} (conf: {r.confidence:.2f})"
                for r in recommendations
            )

            return SizingRecommendation(
                method=primary_method,
                recommended_size=combined_size,
                recommended_risk_amount=combined_risk,
                confidence=combined_confidence,
                reasoning=reasoning,
                constraints_applied=list(set(all_constraints)),
            )

        elif method == "best_confidence":
            # 选择置信度最高的推荐
            return max(recommendations, key=lambda r: r.confidence)

        elif method == "conservative":
            # 选择最保守的推荐（最小仓位）
            return min(recommendations, key=lambda r: r.recommended_size)

        else:
            # 默认使用第一个
            return recommendations[0]

    def _apply_global_constraints(
        self,
        recommended_size: float,
        market_id: str,
        portfolio: PortfolioState,
        entry_price: float,
    ) -> Tuple[float, List[str]]:
        """应用全局约束"""
        constraints = []
        final_size = recommended_size

        # 1. 单市场最大仓位限制
        max_single_position = portfolio.total_capital * self.config.max_single_position_pct
        if final_size > max_single_position:
            final_size = max_single_position
            constraints.append(f"Single position cap: {self.config.max_single_position_pct:.1%}")

        # 2. 总敞口限制
        current_exposure = sum(p.size * p.entry_price for p in portfolio.positions.values())
        new_exposure = current_exposure + final_size
        max_total_exposure = portfolio.total_capital * self.config.max_total_exposure_pct

        if new_exposure > max_total_exposure:
            available_exposure = max_total_exposure - current_exposure
            final_size = max(0, available_exposure)
            constraints.append(f"Total exposure cap: {self.config.max_total_exposure_pct:.1%}")

        # 3. 可用资金限制
        if final_size > portfolio.available_capital:
            final_size = portfolio.available_capital
            constraints.append("Available capital limit")

        # 4. 最小交易规模限制
        if final_size > 0 and final_size < self.config.min_trade_size:
            final_size = 0
            constraints.append(f"Minimum trade size: ${self.config.min_trade_size:.2f}")

        return final_size, constraints
