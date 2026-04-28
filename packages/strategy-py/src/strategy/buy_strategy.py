"""
买入策略决策引擎 - 综合多种信号决定是否买入

该模块实现了多维度信号综合评估系统，用于决策是否执行买入操作。
主要评估维度包括：赔率偏向、时间衰减、订单簿压力、资金流向和信息优势。
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Callable, Any, Tuple
from decimal import Decimal

# Configure logging
logger = logging.getLogger(__name__)


class SignalStrength(Enum):
    """信号强度等级"""
    VERY_STRONG = 5
    STRONG = 4
    MODERATE = 3
    WEAK = 2
    VERY_WEAK = 1
    NONE = 0


class BuyDecision(Enum):
    """买入决策结果"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    PASS = "pass"
    BLOCKED = "blocked"


@dataclass
class OddsBiasMetrics:
    """赔率偏向指标"""
    implied_probability: float  # 隐含概率
    estimated_true_probability: float  # 估计的真实概率
    edge: float  # 赔率优势 (estimated - implied)
    confidence: float  # 置信度 0-1

    def is_favorable(self, min_edge: float = 0.05) -> bool:
        """检查赔率是否有利"""
        return self.edge >= min_edge and self.confidence >= 0.5


@dataclass
class TimeDecayMetrics:
    """时间衰减指标"""
    time_to_expiry: timedelta  # 到期时间
    theta_decay_rate: float  # 时间衰减率 (每日)
    optimal_holding_period: timedelta  # 最优持仓周期
    urgency_score: float  # 紧急程度 0-1

    def is_urgent(self, threshold: float = 0.7) -> bool:
        """检查是否紧急"""
        return self.urgency_score >= threshold


@dataclass
class OrderbookPressureMetrics:
    """订单簿压力指标"""
    bid_ask_spread: float  # 买卖价差
    bid_depth: float  # 买盘深度
    ask_depth: float  # 卖盘深度
    imbalance_ratio: float  # 买卖盘不平衡比例 (-1 to 1, positive = more bids)
    price_impact: float  # 价格冲击估计

    def is_buying_pressure(self, threshold: float = 0.3) -> bool:
        """检查是否有买盘压力"""
        return self.imbalance_ratio >= threshold


@dataclass
class CapitalFlowMetrics:
    """资金流向指标"""
    smart_money_flow: float  # 聪明钱流向
    retail_flow: float  # 散户流向
    institutional_flow: float  # 机构流向
    flow_strength: float  # 流向强度 0-1
    trend_alignment: float  # 趋势一致性 (-1 to 1)

    def is_smart_money_buying(self, threshold: float = 0.5) -> bool:
        """检查聪明钱是否在买入"""
        return self.smart_money_flow > threshold and self.flow_strength >= 0.3


@dataclass
class InformationEdgeMetrics:
    """信息优势指标"""
    price_volume_divergence: float  # 价量背离度 (-1 to 1)
    unusual_activity_score: float  # 异常活动分数 0-1
    news_sentiment: float  # 新闻情绪 -1 to 1
    social_sentiment: float  # 社交媒体情绪 -1 to 1
    composite_score: float  # 综合信息优势分数 0-1

    def has_edge(self, threshold: float = 0.6) -> bool:
        """检查是否有信息优势"""
        return self.composite_score >= threshold


@dataclass
class SportsMomentumMetrics:
    """体育比赛动量指标"""
    score_diff: int  # 比分差距
    time_remaining: int  # 剩余时间（分钟）
    game_status: str  # 比赛状态
    momentum_score: float  # 动量分数 0-1
    event_strength: str  # 事件强度 "strong" | "moderate" | "weak"

    def is_strong_momentum(self) -> bool:
        return self.event_strength == "strong" and self.momentum_score >= 0.7


@dataclass
class MarketContext:
    """市场环境上下文"""
    market_id: str
    outcome_id: str
    current_price: float
    current_odds: float
    timestamp: datetime
    volume_24h: float
    liquidity: float

    # 评估维度
    odds_bias: Optional[OddsBiasMetrics] = None
    time_decay: Optional[TimeDecayMetrics] = None
    orderbook_pressure: Optional[OrderbookPressureMetrics] = None
    capital_flow: Optional[CapitalFlowMetrics] = None
    information_edge: Optional[InformationEdgeMetrics] = None
    sports_momentum: Optional[SportsMomentumMetrics] = None


@dataclass
class RiskCheckResult:
    """风险检查结果"""
    passed: bool
    failed_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    adjusted_position_size: Optional[float] = None
    max_position_size: Optional[float] = None


@dataclass
class BuyDecisionOutput:
    """买入决策输出"""
    decision: BuyDecision
    confidence: float  # 0-1
    position_size: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    signal_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# Type aliases for callbacks
SignalGenerator = Callable[[MarketContext], Tuple[SignalStrength, float, str]]
RiskManager = Any  # Forward reference, will be properly typed in implementation


@dataclass
class BuyStrategyConfig:
    """买入策略配置"""
    # 死亡区间配置
    death_zone_min: float = 0.60
    death_zone_max: float = 0.85

    # 赔率偏向权重
    odds_bias_weight: float = 0.25
    min_odds_edge: float = 0.05

    # 时间衰减权重
    time_decay_weight: float = 0.15

    # 订单簿压力权重
    orderbook_weight: float = 0.20
    min_imbalance_ratio: float = 0.3

    # 资金流向权重
    capital_flow_weight: float = 0.20
    min_smart_money_threshold: float = 0.5

    # 信息优势权重
    information_edge_weight: float = 0.10
    min_information_score: float = 0.6

    # 体育动量权重
    sports_momentum_weight: float = 0.15
    min_sports_momentum_score: float = 0.5

    # 决策阈值
    strong_buy_threshold: float = 0.80
    buy_threshold: float = 0.65
    hold_threshold: float = 0.45

    # 仓位管理
    max_single_position_pct: float = 0.10  # 单笔最大10%
    max_total_positions: int = 20
    max_correlated_positions: int = 5

    # 风险控制
    enable_death_zone_check: bool = True
    enable_correlation_check: bool = True
    enable_liquidity_check: bool = True
    min_liquidity: float = 10000.0


class BuyStrategy:
    """买入策略决策引擎 - 综合多种信号决定是否买入

    评估维度：
    1. 赔率偏向 (odds_bias) - 赔率是否偏离真实概率
    2. 时间衰减 (time_decay) - 到期时间价值评估
    3. 订单簿压力 (orderbook_pressure) - 买卖盘不平衡
    4. 资金流向 (capital_flow) - 聪明钱动向
    5. 信息优势 (information_edge) - 价格-成交量背离
    6. 体育动量 (sports_momentum) - 实时比分驱动的动量信号

    风险检查：
    - 死亡区间检查 ($0.60-$0.85 不交易)
    - 单笔持仓上限
    - 总持仓限制
    - 市场相关性检查
    """

    def __init__(self,
                 signal_generators: List[SignalGenerator],
                 risk_manager: Any,
                 config: Optional[BuyStrategyConfig] = None):
        """
        初始化买入策略引擎

        Args:
            signal_generators: 信号生成器列表
            risk_manager: 风险管理器实例
            config: 策略配置，使用默认配置如果未提供
        """
        self.signal_generators = signal_generators
        self.risk_manager = risk_manager
        self.config = config or BuyStrategyConfig()

        # 信号历史记录（用于评估信号质量）
        self._signal_history: Dict[str, List[Dict]] = {}

        # 评分权重缓存
        self._weights = {
            'odds_bias': self.config.odds_bias_weight,
            'time_decay': self.config.time_decay_weight,
            'orderbook': self.config.orderbook_weight,
            'capital_flow': self.config.capital_flow_weight,
            'information_edge': self.config.information_edge_weight,
            'sports_momentum': self.config.sports_momentum_weight,
        }

        # 权重归一化
        total_weight = sum(self._weights.values())
        if total_weight > 0:
            self._weights = {k: v / total_weight for k, v in self._weights.items()}

        logger.info(f"BuyStrategy initialized with {len(signal_generators)} signal generators")
        logger.info(f"Weight configuration: {self._weights}")

    async def evaluate(self, context: MarketContext) -> BuyDecisionOutput:
        """
        评估市场上下文并做出买入决策

        Args:
            context: 市场环境上下文

        Returns:
            BuyDecisionOutput: 买入决策输出
        """
        logger.info(f"Evaluating market {context.market_id} at price {context.current_price}")

        # 1. 死亡区间检查
        if self._is_in_death_zone(context.current_price):
            return self._create_blocked_decision(
                context, "Price in death zone ($0.60-$0.85), no trade allowed"
            )

        # 2. 基础风险检查
        risk_check = await self._perform_risk_checks(context)
        if not risk_check.passed:
            return self._create_blocked_decision(
                context, f"Risk checks failed: {', '.join(risk_check.failed_checks)}"
            )

        # 3. 生成并评估信号
        signal_scores = await self._evaluate_signals(context)

        # 4. 计算综合评分
        composite_score = self._calculate_composite_score(signal_scores, context)

        # 5. 基于评分做出决策
        decision, confidence = self._make_decision(composite_score, context)

        # 6. 计算仓位大小
        position_size = self._calculate_position_size(
            decision, context, risk_check, composite_score
        )

        # 7. 计算止损止盈
        stop_loss, take_profit = self._calculate_exit_levels(
            context, position_size, decision
        )

        # 8. 构建决策输出
        output = BuyDecisionOutput(
            decision=decision,
            confidence=confidence,
            position_size=position_size,
            entry_price=context.current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=self._generate_reasoning(signal_scores, context, decision),
            risk_warnings=risk_check.warnings,
            signal_scores=signal_scores,
            timestamp=datetime.now()
        )

        logger.info(f"Buy decision for {context.market_id}: {decision.value} "
                   f"(confidence: {confidence:.2f}, size: {position_size:.4f})")

        return output

    def _is_in_death_zone(self, price: float) -> bool:
        """
        检查价格是否在死亡区间 ($0.60-$0.85)

        死亡区间的特点：
        - 赔率既不高也不低，处于尴尬区间
        - 缺乏明确的方向性优势
        - 风险收益比不佳
        """
        if not self.config.enable_death_zone_check:
            return False
        return self.config.death_zone_min <= price <= self.config.death_zone_max

    async def _perform_risk_checks(self, context: MarketContext) -> RiskCheckResult:
        """执行风险检查"""
        failed_checks = []
        warnings = []

        # 1. 流动性检查
        if self.config.enable_liquidity_check:
            if context.liquidity < self.config.min_liquidity:
                failed_checks.append(f"Insufficient liquidity: {context.liquidity} < {self.config.min_liquidity}")

        # 2. 使用risk_manager进行额外检查
        if self.risk_manager:
            try:
                # 检查持仓限制
                if hasattr(self.risk_manager, 'check_position_limits'):
                    position_check = await self.risk_manager.check_position_limits(context.market_id)
                    if not position_check.get('allowed', True):
                        failed_checks.append(f"Position limit exceeded: {position_check.get('reason', '')}")

                # 检查相关性
                if self.config.enable_correlation_check and hasattr(self.risk_manager, 'check_correlation'):
                    corr_check = await self.risk_manager.check_correlation(context.market_id)
                    if corr_check.get('high_correlation', False):
                        warnings.append(f"High correlation with {corr_check.get('correlated_markets', [])}")

            except Exception as e:
                logger.warning(f"Risk manager check failed: {e}")
                warnings.append(f"Risk check error: {str(e)}")

        return RiskCheckResult(
            passed=len(failed_checks) == 0,
            failed_checks=failed_checks,
            warnings=warnings
        )

    async def _evaluate_signals(self, context: MarketContext) -> Dict[str, float]:
        """
        评估所有信号生成器

        Returns:
            信号名称到分数的字典 (0-1)
        """
        scores = {}

        # 1. 评估所有信号生成器
        for generator in self.signal_generators:
            try:
                signal_strength, confidence, description = await self._call_signal_generator(generator, context)

                # 将信号强度转换为分数
                score = signal_strength.value / 5.0 * confidence
                scores[f"signal_{id(generator)}"] = min(1.0, max(0.0, score))

                logger.debug(f"Signal {generator.__name__ if hasattr(generator, '__name__') else id(generator)}: "
                            f"strength={signal_strength.name}, confidence={confidence:.2f}")

            except Exception as e:
                logger.warning(f"Signal generator failed: {e}")
                continue

        # 2. 评估各个维度的指标（如果context中有）
        if context.odds_bias:
            scores['odds_bias'] = self._evaluate_odds_bias(context.odds_bias)

        if context.time_decay:
            scores['time_decay'] = self._evaluate_time_decay(context.time_decay)

        if context.orderbook_pressure:
            scores['orderbook'] = self._evaluate_orderbook(context.orderbook_pressure)

        if context.capital_flow:
            scores['capital_flow'] = self._evaluate_capital_flow(context.capital_flow)

        if context.information_edge:
            scores['information_edge'] = self._evaluate_information_edge(context.information_edge)

        if context.sports_momentum:
            scores['sports_momentum'] = self._evaluate_sports_momentum(context.sports_momentum)

        return scores

    async def _call_signal_generator(self, generator: SignalGenerator, context: MarketContext) -> Tuple[SignalStrength, float, str]:
        """调用信号生成器（支持同步和异步）"""
        import inspect

        if inspect.iscoroutinefunction(generator):
            return await generator(context)
        else:
            return generator(context)

    def _evaluate_odds_bias(self, metrics: OddsBiasMetrics) -> float:
        """评估赔率偏向分数"""
        # 基于edge和confidence计算分数
        edge_score = min(1.0, metrics.edge / 0.05)  # 5% edge为满分
        confidence_score = metrics.confidence
        base = edge_score * confidence_score
        if not metrics.is_favorable(self.config.min_odds_edge):
            return base * 0.5  # 未达标时减半，而非归零
        return base

    def _evaluate_time_decay(self, metrics: TimeDecayMetrics) -> float:
        """评估时间衰减分数。

        此处只做平滑评分，不做硬拦截。
        时间拦截由上层 ExpiryPolicy 统一处理。
        """
        days_to_expiry = metrics.time_to_expiry.total_seconds() / 86400

        if days_to_expiry <= 0:
            return 0.0  # 已过期

        # 基于 urgency_score 和剩余天数做平滑评分
        urgency = metrics.urgency_score  # 0.0 ~ 1.0
        # 将天数映射到 0-1（假设30天为参考上限）
        days_norm = min(1.0, days_to_expiry / 30.0)
        # urgency 越高（临近到期），评分越高；但天数太少会衰减
        if days_to_expiry < 0.5:  # 不到12小时
            return 0.3 + urgency * 0.4
        elif days_to_expiry <= 3:
            return 0.5 + urgency * 0.4
        else:
            return 0.6 + urgency * 0.2 * (1.0 - days_norm * 0.5)

    def _evaluate_orderbook(self, metrics: OrderbookPressureMetrics) -> float:
        """评估订单簿压力分数"""
        # 基于不平衡程度评分
        imbalance_score = (metrics.imbalance_ratio + 1) / 2  # 归一化到0-1

        # 考虑价格冲击
        impact_penalty = 1.0 - min(1.0, metrics.price_impact / 0.02)  # 2%冲击为上限

        base = imbalance_score * impact_penalty
        if not metrics.is_buying_pressure(self.config.min_imbalance_ratio):
            return base * 0.5  # 未达标时减半
        return base

    def _evaluate_capital_flow(self, metrics: CapitalFlowMetrics) -> float:
        """评估资金流向分数"""
        # 聪明钱流向评分
        smart_score = (metrics.smart_money_flow + 1) / 2

        # 趋势一致性加分
        alignment_bonus = (metrics.trend_alignment + 1) / 2

        # 流向强度（保底0.2避免归零）
        strength_factor = max(0.2, metrics.flow_strength)

        base = smart_score * (0.6 + 0.4 * alignment_bonus) * strength_factor
        if not metrics.is_smart_money_buying(self.config.min_smart_money_threshold):
            return base * 0.5  # 未达标时减半
        return base

    def _evaluate_information_edge(self, metrics: InformationEdgeMetrics) -> float:
        """评估信息优势分数"""
        base_score = metrics.composite_score

        # 异常活动加分
        anomaly_bonus = metrics.unusual_activity_score * 0.2

        # 情绪一致性检查
        sentiment_alignment = 1.0 - abs(metrics.news_sentiment - metrics.social_sentiment)
        alignment_bonus = sentiment_alignment * 0.1

        final_score = base_score + anomaly_bonus + alignment_bonus
        return min(1.0, final_score)

    def _evaluate_sports_momentum(self, metrics: SportsMomentumMetrics) -> float:
        """评估体育动量分数"""
        if metrics.event_strength == "strong":
            base = 0.9
        elif metrics.event_strength == "moderate":
            base = 0.6
        else:
            base = 0.3

        # 时间衰减：比赛越接近尾声，信号越确定
        # Note: time_remaining may be inaccurate (e.g., extra time not included)
        time_factor = 1.0
        if metrics.time_remaining <= 15:
            time_factor = 1.0
        elif metrics.time_remaining <= 30:
            time_factor = 0.85
        else:
            time_factor = 0.7

        # 比分差距越大，确定性越高
        lead_factor = min(1.0, 0.3 + metrics.score_diff * 0.2)

        return base * time_factor * lead_factor

    def _calculate_composite_score(self,
                                   signal_scores: Dict[str, float],
                                   context: MarketContext) -> float:
        """计算综合评分"""
        if not signal_scores:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        # 按维度分类评分
        dimension_scores = {
            'odds_bias': [],
            'time_decay': [],
            'orderbook': [],
            'capital_flow': [],
            'information_edge': [],
            'signals': []
        }

        for name, score in signal_scores.items():
            categorized = False
            for dim in dimension_scores.keys():
                if dim in name.lower():
                    dimension_scores[dim].append(score)
                    categorized = True
                    break
            if not categorized:
                dimension_scores['signals'].append(score)

        # 计算各维度平均分
        dimension_avgs = {}
        for dim, scores in dimension_scores.items():
            if scores:
                dimension_avgs[dim] = sum(scores) / len(scores)

        # 加权计算综合评分
        for dim, avg_score in dimension_avgs.items():
            weight = self._weights.get(dim, 0.2)
            weighted_sum += avg_score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # 归一化到0-1
        composite_score = weighted_sum / total_weight

        # 应用上下文调整
        adjusted_score = self._apply_context_adjustments(composite_score, context)

        return max(0.0, min(1.0, adjusted_score))

    def _apply_context_adjustments(self, base_score: float, context: MarketContext) -> float:
        """根据上下文调整评分"""
        adjusted = base_score

        # 流动性惩罚
        if context.liquidity < self.config.min_liquidity * 2:
            liquidity_penalty = 0.1 * (1 - context.liquidity / (self.config.min_liquidity * 2))
            adjusted -= liquidity_penalty

        # 高波动性惩罚（可以通过volume_24h/liquidity估计）
        if context.liquidity > 0:
            volume_liquidity_ratio = context.volume_24h / context.liquidity
            if volume_liquidity_ratio > 2.0:  # 高换手率
                adjusted -= 0.05  # 轻微惩罚

        return adjusted

    def _make_decision(self, composite_score: float, context: MarketContext) -> Tuple[BuyDecision, float]:
        """基于综合评分做出决策"""
        # 根据阈值确定决策
        if composite_score >= self.config.strong_buy_threshold:
            decision = BuyDecision.STRONG_BUY
            confidence = min(1.0, composite_score + 0.1)  # 轻微提升置信度
        elif composite_score >= self.config.buy_threshold:
            decision = BuyDecision.BUY
            confidence = composite_score
        elif composite_score >= self.config.hold_threshold:
            decision = BuyDecision.HOLD
            confidence = 1.0 - composite_score  # 越低越不确定
        else:
            decision = BuyDecision.PASS
            confidence = 0.5  # 明确的放弃决策

        return decision, confidence

    def _calculate_position_size(self,
                                  decision: BuyDecision,
                                  context: MarketContext,
                                  risk_check: RiskCheckResult,
                                  composite_score: float) -> float:
        """计算仓位大小"""
        # 基础仓位（基于决策强度）
        if decision == BuyDecision.STRONG_BUY:
            base_size = self.config.max_single_position_pct
        elif decision == BuyDecision.BUY:
            base_size = self.config.max_single_position_pct * 0.7
        elif decision == BuyDecision.HOLD:
            # 观望时可能建仓一小部分
            base_size = self.config.max_single_position_pct * 0.3
        else:
            return 0.0

        # 根据综合评分调整
        score_adjustment = composite_score  # 0-1
        adjusted_size = base_size * (0.5 + 0.5 * score_adjustment)

        # 应用风险调整
        if risk_check.adjusted_position_size is not None:
            adjusted_size = min(adjusted_size, risk_check.adjusted_position_size)

        if risk_check.max_position_size is not None:
            adjusted_size = min(adjusted_size, risk_check.max_position_size)

        # 确保不超过最大限制
        adjusted_size = min(adjusted_size, self.config.max_single_position_pct)

        return max(0.0, adjusted_size)

    def _calculate_exit_levels(self,
                                context: MarketContext,
                                position_size: float,
                                decision: BuyDecision) -> Tuple[Optional[float], Optional[float]]:
        """计算止损和止盈水平"""
        if position_size == 0 or decision in [BuyDecision.PASS, BuyDecision.BLOCKED]:
            return None, None

        current_price = context.current_price

        # 止损：基于决策强度和风险承受能力
        if decision == BuyDecision.STRONG_BUY:
            stop_loss_pct = 0.10  # 10% 止损
        elif decision == BuyDecision.BUY:
            stop_loss_pct = 0.08  # 8% 止损
        else:
            stop_loss_pct = 0.05  # 5% 止损（观望时更保守）

        # 对于二元市场，止损不能超过当前价格
        stop_loss = max(0.01, current_price * (1 - stop_loss_pct))

        # 止盈：风险收益比至少1:2
        risk = current_price - stop_loss
        take_profit = current_price + (risk * 2)

        # 止盈不能超过1.0（二元市场）
        take_profit = min(0.99, take_profit)

        return stop_loss, take_profit

    def _generate_reasoning(self,
                           signal_scores: Dict[str, float],
                           context: MarketContext,
                           decision: BuyDecision) -> List[str]:
        """生成决策理由"""
        reasoning = []

        # 添加各维度评估
        if context.odds_bias:
            edge_pct = context.odds_bias.edge * 100
            reasoning.append(f"Odds bias: {edge_pct:.2f}% edge (confidence: {context.odds_bias.confidence:.2f})")

        if context.time_decay:
            days = context.time_decay.time_to_expiry.total_seconds() / 86400
            reasoning.append(f"Time to expiry: {days:.1f} days (urgency: {context.time_decay.urgency_score:.2f})")

        if context.orderbook_pressure:
            imb = context.orderbook_pressure.imbalance_ratio
            reasoning.append(f"Orderbook imbalance: {imb:+.2f} (positive = buying pressure)")

        if context.capital_flow:
            smf = context.capital_flow.smart_money_flow
            reasoning.append(f"Smart money flow: {smf:+.2f} (strength: {context.capital_flow.flow_strength:.2f})")

        if context.information_edge:
            ies = context.information_edge.composite_score
            reasoning.append(f"Information edge: {ies:.2f} (unusual activity: {context.information_edge.unusual_activity_score:.2f})")

        if context.sports_momentum:
            sms = context.sports_momentum.momentum_score
            reasoning.append(
                f"Sports momentum: {sms:.2f} ({context.sports_momentum.event_strength}, "
                f"score_diff={context.sports_momentum.score_diff}, remaining={context.sports_momentum.time_remaining}m)"
            )

        # 添加信号分数摘要
        if signal_scores:
            top_signals = sorted(signal_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            signal_summary = ", ".join([f"{k}={v:.2f}" for k, v in top_signals])
            reasoning.append(f"Top signals: {signal_summary}")

        # 添加决策解释
        if decision == BuyDecision.STRONG_BUY:
            reasoning.append("Decision: STRONG BUY - Multiple favorable signals with high confidence")
        elif decision == BuyDecision.BUY:
            reasoning.append("Decision: BUY - Favorable conditions with acceptable risk")
        elif decision == BuyDecision.HOLD:
            reasoning.append("Decision: HOLD - Mixed signals, waiting for clearer setup")
        elif decision == BuyDecision.PASS:
            reasoning.append("Decision: PASS - Unfavorable conditions, skip this opportunity")

        return reasoning

    def _create_blocked_decision(self, context: MarketContext, reason: str) -> BuyDecisionOutput:
        """创建被阻止的决策输出"""
        return BuyDecisionOutput(
            decision=BuyDecision.BLOCKED,
            confidence=0.0,
            position_size=0.0,
            entry_price=context.current_price,
            stop_loss=None,
            take_profit=None,
            reasoning=[f"Blocked: {reason}"],
            risk_warnings=[],
            signal_scores={},
            timestamp=datetime.now()
        )

    def update_config(self, new_config: BuyStrategyConfig) -> None:
        """更新策略配置"""
        self.config = new_config

        # 更新权重缓存
        self._weights = {
            'odds_bias': new_config.odds_bias_weight,
            'time_decay': new_config.time_decay_weight,
            'orderbook': new_config.orderbook_weight,
            'capital_flow': new_config.capital_flow_weight,
            'information_edge': new_config.information_edge_weight,
            'sports_momentum': new_config.sports_momentum_weight,
        }

        # 权重归一化
        total_weight = sum(self._weights.values())
        if total_weight > 0:
            self._weights = {k: v / total_weight for k, v in self._weights.items()}

        logger.info("BuyStrategy configuration updated")

    def get_signal_history(self, market_id: Optional[str] = None) -> Dict[str, List[Dict]]:
        """获取信号历史记录"""
        if market_id:
            return {market_id: self._signal_history.get(market_id, [])}
        return self._signal_history.copy()

    def clear_signal_history(self, market_id: Optional[str] = None) -> None:
        """清除信号历史记录"""
        if market_id:
            self._signal_history.pop(market_id, None)
        else:
            self._signal_history.clear()
        logger.info(f"Signal history cleared{' for ' + market_id if market_id else ''}")
