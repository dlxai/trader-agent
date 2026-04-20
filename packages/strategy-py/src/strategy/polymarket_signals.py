"""
Polymarket Prediction Market Signal Generators

专为预测市场设计的信号生成器，完全摒弃股票技术指标(RSI、MA、布林带等)。
所有计算基于概率(0-1)而非价格。

核心策略:
1. Odds Bias - 赔率偏差信号
2. Time Decay - 时间衰减信号
3. Orderbook Pressure - 订单簿压力信号
4. Capital Flow - 资金流向信号
5. Information Edge - 信息优势信号
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS - 信号类型和强度
# =============================================================================

class SignalType(Enum):
    """信号类型枚举"""
    ODDS_BIAS = "odds_bias"           # 赔率偏差
    TIME_DECAY = "time_decay"          # 时间衰减
    ORDERBOOK_PRESSURE = "orderbook_pressure"  # 订单簿压力
    CAPITAL_FLOW = "capital_flow"      # 资金流向
    INFORMATION_EDGE = "information_edge"  # 信息优势
    COMPOUND = "compound"              # 复合信号


class SignalStrength(Enum):
    """信号强度枚举"""
    VERY_WEAK = 0.1
    WEAK = 0.3
    MODERATE = 0.5
    STRONG = 0.7
    VERY_STRONG = 0.9


class SignalDirection(Enum):
    """信号方向"""
    BUY = 1       # 买入/看涨
    SELL = -1     # 卖出/看跌
    HOLD = 0      # 观望


# =============================================================================
# DATA CLASSES - 信号数据结构
# =============================================================================

@dataclass
class MarketState:
    """市场状态数据"""
    market_id: str
    token_id: str
    yes_price: Decimal  # Yes token价格 (0-1)
    no_price: Decimal   # No token价格 (0-1)
    spread: Decimal     # 买卖价差
    volume_24h: Decimal
    liquidity: Decimal
    last_update: datetime

    @property
    def implied_probability(self) -> Decimal:
        """从价格推导的隐含概率"""
        return self.yes_price

    @property
    def odds_decimal(self) -> Decimal:
        """十进制赔率"""
        if self.yes_price == 0:
            return Decimal('inf')
        return Decimal('1') / self.yes_price


@dataclass
class OrderBookLevel:
    """订单簿层级"""
    price: Decimal
    size: Decimal
    count: int


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    market_id: str
    token_id: str
    bids: List[OrderBookLevel]  # 买单
    asks: List[OrderBookLevel]  # 卖单
    timestamp: datetime

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """最优买价"""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """最优卖价"""
        return self.asks[0] if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """中间价"""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return None

    @property
    def bid_ask_imbalance(self) -> Decimal:
        """买卖盘不平衡度 (-1 to 1, 正值表示买盘更强)"""
        total_bid_size = sum(level.size for level in self.bids)
        total_ask_size = sum(level.size for level in self.asks)
        total = total_bid_size + total_ask_size
        if total == 0:
            return Decimal('0')
        return (total_bid_size - total_ask_size) / total


@dataclass
class Trade:
    """单笔交易"""
    trade_id: str
    market_id: str
    token_id: str
    side: str  # 'buy' or 'sell'
    size: Decimal
    price: Decimal
    timestamp: datetime
    trader_address: Optional[str] = None


@dataclass
class CapitalFlowMetrics:
    """资金流向指标"""
    market_id: str
    period_hours: int
    total_inflow: Decimal
    total_outflow: Decimal
    net_flow: Decimal
    smart_money_inflow: Decimal
    smart_money_outflow: Decimal
    whale_trades: List[Trade]
    timestamp: datetime

    @property
    def flow_ratio(self) -> Decimal:
        """资金流入流出比"""
        if self.total_outflow == 0:
            return Decimal('inf') if self.total_inflow > 0 else Decimal('1')
        return self.total_inflow / self.total_outflow

    @property
    def smart_money_ratio(self) -> Decimal:
        """聪明钱净流入占比"""
        if self.net_flow == 0:
            return Decimal('0')
        smart_net = self.smart_money_inflow - self.smart_money_outflow
        return smart_net / self.net_flow


@dataclass
class EventInfo:
    """事件信息"""
    event_id: str
    event_name: str
    event_type: str  # 'sports', 'politics', 'crypto', etc.
    expected_resolution: datetime
    actual_resolution: Optional[datetime] = None
    result: Optional[str] = None
    source: Optional[str] = None
    confidence: Decimal = Decimal('0.5')


@dataclass
class PolymarketSignal:
    """
    Polymarket预测市场完整信号数据结构

    这是信号生成器的核心输出，包含完整的信号元数据、
    置信度评估和执行建议。
    """
    # 基础标识
    signal_id: str
    timestamp: datetime
    market_id: str
    token_id: str

    # 信号分类
    signal_type: SignalType
    direction: SignalDirection
    strength: SignalStrength

    # 概率和赔率
    current_probability: Decimal  # 当前市场隐含概率
    estimated_probability: Decimal  # 估计的真实概率
    edge: Decimal  # 概率优势 (estimated - current)
    odds: Decimal  # 当前赔率

    # 信号元数据
    confidence: Decimal  # 整体置信度 (0-1)
    time_horizon_hours: Optional[int] = None  # 预期持有时间

    # 信号来源详情
    source_data: Dict[str, Any] = field(default_factory=dict)

    # 执行建议
    recommended_size: Optional[Decimal] = None  # 建议仓位大小
    kelly_fraction: Optional[Decimal] = None  # 凯利公式建议比例
    max_position_size: Optional[Decimal] = None  # 最大仓位限制

    # 风险管理
    stop_loss_probability: Optional[Decimal] = None  # 止损概率阈值
    take_profit_probability: Optional[Decimal] = None  # 止盈概率阈值

    # 备注和解释
    reasoning: str = ""  # 信号生成逻辑说明
    warnings: List[str] = field(default_factory=list)  # 风险提示

    def __post_init__(self):
        """验证信号数据一致性"""
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")
        if not 0 <= float(self.current_probability) <= 1:
            raise ValueError(f"Current probability must be between 0 and 1")
        if not 0 <= float(self.estimated_probability) <= 1:
            raise ValueError(f"Estimated probability must be between 0 and 1")

    @property
    def is_actionable(self) -> bool:
        """信号是否可执行（置信度和强度足够）"""
        return (
            self.confidence >= Decimal('0.6') and
            self.strength.value >= SignalStrength.MODERATE.value and
            abs(self.edge) >= Decimal('0.02')
        )

    @property
    def expected_value(self) -> Decimal:
        """计算期望值 (EV)"""
        return calculate_expected_value(
            self.estimated_probability,
            self.odds
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'signal_id': self.signal_id,
            'timestamp': self.timestamp.isoformat(),
            'market_id': self.market_id,
            'token_id': self.token_id,
            'signal_type': self.signal_type.value,
            'direction': self.direction.name,
            'strength': self.strength.name,
            'current_probability': float(self.current_probability),
            'estimated_probability': float(self.estimated_probability),
            'edge': float(self.edge),
            'odds': float(self.odds),
            'confidence': float(self.confidence),
            'is_actionable': self.is_actionable,
            'expected_value': float(self.expected_value),
            'reasoning': self.reasoning,
        }


# =============================================================================
# PROTOCOLS - 数据源协议
# =============================================================================

@runtime_checkable
class MarketDataSource(Protocol):
    """市场数据源协议"""

    async def get_market_state(self, market_id: str, token_id: str) -> MarketState:
        """获取市场当前状态"""
        ...

    async def get_orderbook(self, market_id: str, token_id: str, depth: int = 10) -> OrderBookSnapshot:
        """获取订单簿快照"""
        ...

    async def get_recent_trades(
        self,
        market_id: str,
        token_id: str,
        hours: int = 24
    ) -> List[Trade]:
        """获取近期交易记录"""
        ...


@runtime_checkable
class EventDataSource(Protocol):
    """事件数据源协议"""

    async def get_event_info(self, event_id: str) -> EventInfo:
        """获取事件信息"""
        ...

    async def get_event_status(self, event_id: str) -> Dict[str, Any]:
        """获取事件实时状态"""
        ...

    async def check_result_availability(self, event_id: str) -> Tuple[bool, Optional[str]]:
        """检查结果是否已可用（提前结果检测）"""
        ...


@runtime_checkable
class AccountDataSource(Protocol):
    """账户数据源协议（聪明钱地址追踪）"""

    async def get_smart_money_accounts(
        self,
        min_win_rate: Decimal = Decimal('0.6'),
        min_trades: int = 10
    ) -> List[str]:
        """获取聪明钱地址列表"""
        ...

    async def get_account_trades(
        self,
        account_address: str,
        market_id: Optional[str] = None,
        hours: int = 24
    ) -> List[Trade]:
        """获取账户交易历史"""
        ...

    async def get_account_performance(
        self,
        account_address: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """获取账户历史表现"""
        ...


# =============================================================================
# HELPER FUNCTIONS - 辅助计算函数
# =============================================================================

def calculate_kelly_criterion(edge: Decimal, odds: Decimal) -> Decimal:
    """
    凯利公式计算最优仓位比例

    f* = (bp - q) / b
    其中:
    - b = 净赔率 (odds - 1)
    - p = 获胜概率
    - q = 失败概率 = 1 - p

    Args:
        edge: 概率优势 (estimated_prob - market_prob)
        odds: 当前赔率 (decimal odds)

    Returns:
        建议仓位比例 (0-1)，负值表示不应下注
    """
    if odds <= 1:
        return Decimal('0')

    b = odds - 1  # 净赔率
    p = edge  # 这里edge已经是概率差，我们假设estimated_prob = market_prob + edge
    # 但为了计算Kelly，我们需要estimated_prob
    # 这里简化处理，假设edge是相对于公平概率的优势

    # 重新解读: edge = estimated_prob - market_prob
    # 我们需要 estimated_prob = market_prob + edge
    # 但这里没有market_prob参数，所以我们假设edge就是estimated_prob

    q = 1 - p

    if b <= 0:
        return Decimal('0')

    kelly = (b * p - q) / b

    # 限制在合理范围内
    return max(Decimal('-1'), min(Decimal('1'), kelly))


def calculate_expected_value(probability: Decimal, odds: Decimal) -> Decimal:
    """
    计算期望值 (EV)

    EV = (Probability of Win × Amount Won per Bet) - (Probability of Loss × Amount Lost per Bet)

    简化: EV = p * (odds - 1) - (1 - p) * 1 = p * odds - 1

    Args:
        probability: 估计的获胜概率 (0-1)
        odds: 十进制赔率

    Returns:
        期望值，正值表示有利可图的投注
    """
    return probability * odds - 1


def time_to_event_decay(hours_remaining: float) -> float:
    """
    时间衰减因子计算

    随着事件临近，价格会趋向于真实结果，时间价值递减。
    使用指数衰减模型：decay = 1 - exp(-lambda * t)

    Args:
        hours_remaining: 距离事件发生的剩余小时数

    Returns:
        衰减因子 (0-1)，值越大表示时间价值越低
    """
    if hours_remaining <= 0:
        return 1.0

    # lambda = 0.1 表示约7小时后衰减到50%
    lambda_param = 0.1
    decay = 1.0 - math.exp(-lambda_param * hours_remaining)

    return min(1.0, max(0.0, decay))


def calculate_implied_probability(odds: Decimal) -> Decimal:
    """
    从赔率计算隐含概率

    隐含概率 = 1 / 赔率

    Args:
        odds: 十进制赔率

    Returns:
        隐含概率 (0-1)
    """
    if odds <= 0:
        return Decimal('0')
    return Decimal('1') / odds


def calculate_margin_adjusted_probability(
    yes_price: Decimal,
    no_price: Decimal
) -> Decimal:
    """
    计算去除庄家抽水后的真实概率估计

    庄家抽水 = (1/yes_price + 1/no_price) - 1
    调整后的概率 = 隐含概率 / (1 + 抽水)

    Args:
        yes_price: Yes token价格
        no_price: No token价格

    Returns:
        调整后的真实概率估计
    """
    if yes_price <= 0 or no_price <= 0:
        return Decimal('0.5')

    yes_implied = Decimal('1') / yes_price
    no_implied = Decimal('1') / no_price

    # 庄家抽水 (overround)
    overround = yes_implied + no_implied - 1

    # 调整后的概率
    if overround < 0:
        overround = Decimal('0')

    adjusted = yes_implied / (1 + overround)
    return min(Decimal('1'), max(Decimal('0'), adjusted))


def detect_whales(
    trades: List[Trade],
    threshold_usd: Decimal = Decimal('10000')
) -> List[Trade]:
    """
    检测鲸鱼交易（大额交易）

    Args:
        trades: 交易列表
        threshold_usd: 鲸鱼阈值（美元）

    Returns:
        鲸鱼交易列表
    """
    whales = []
    for trade in trades:
        trade_value = trade.size * trade.price
        if trade_value >= threshold_usd:
            whales.append(trade)
    return whales


def calculate_confidence_score(
    sample_size: int,
    edge: Decimal,
    time_consistency: float,
    data_quality: float = 1.0
) -> Decimal:
    """
    计算信号置信度分数

    基于多个因素:
    - 样本量 (更多数据 = 更高置信度)
    - 概率优势大小
    - 时间一致性
    - 数据质量

    Args:
        sample_size: 样本数量
        edge: 概率优势
        time_consistency: 时间一致性 (0-1)
        data_quality: 数据质量 (0-1)

    Returns:
        置信度分数 (0-1)
    """
    # 样本量因子 (使用对数压缩)
    if sample_size <= 0:
        sample_factor = 0.0
    else:
        sample_factor = min(1.0, math.log10(sample_size) / 3)

    # 概率优势因子
    edge_magnitude = min(1.0, float(abs(edge)) * 5)  # 20% edge = 满分

    # 综合计算
    confidence = (
        sample_factor * 0.3 +
        edge_magnitude * 0.3 +
        time_consistency * 0.2 +
        data_quality * 0.2
    )

    return Decimal(str(min(1.0, max(0.0, confidence))))


# =============================================================================
# SIGNAL GENERATORS - 信号生成器基类
# =============================================================================

class BaseSignalGenerator:
    """信号生成器基类"""

    def __init__(
        self,
        signal_type: SignalType,
        min_confidence: Decimal = Decimal('0.6'),
        min_edge: Decimal = Decimal('0.02'),
        max_signals_per_hour: int = 10
    ):
        """
        初始化信号生成器

        Args:
            signal_type: 信号类型
            min_confidence: 最小置信度阈值
            min_edge: 最小概率优势阈值
            max_signals_per_hour: 每小时最大信号数
        """
        self.signal_type = signal_type
        self.min_confidence = min_confidence
        self.min_edge = min_edge
        self.max_signals_per_hour = max_signals_per_hour
        self._signal_history: List[datetime] = []

        logger.info(
            f"Initialized {self.__class__.__name__} with "
            f"min_confidence={min_confidence}, min_edge={min_edge}"
        )

    def _check_rate_limit(self) -> bool:
        """检查是否超过信号频率限制"""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        self._signal_history = [t for t in self._signal_history if t > cutoff]
        return len(self._signal_history) < self.max_signals_per_hour

    def _record_signal(self):
        """记录信号生成时间"""
        self._signal_history.append(datetime.utcnow())

    def _calculate_strength(self, edge: Decimal, confidence: Decimal) -> SignalStrength:
        """根据边缘和置信度计算信号强度"""
        score = float(edge) * 5 + float(confidence)

        if score >= 1.5:
            return SignalStrength.VERY_STRONG
        elif score >= 1.2:
            return SignalStrength.STRONG
        elif score >= 0.8:
            return SignalStrength.MODERATE
        elif score >= 0.5:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK

    def _determine_direction(self, edge: Decimal) -> SignalDirection:
        """根据边缘确定方向"""
        if edge > self.min_edge:
            return SignalDirection.BUY
        elif edge < -self.min_edge:
            return SignalDirection.SELL
        else:
            return SignalDirection.HOLD

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成交易信号（子类必须实现）

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs: 额外参数

        Returns:
            信号列表
        """
        raise NotImplementedError("Subclasses must implement generate_signals")


# =============================================================================
# 1. ODDS BIAS SIGNAL GENERATOR - 赔率偏差信号
# =============================================================================

class OddsBiasSignalGenerator(BaseSignalGenerator):
    """
    赔率偏差信号生成器

    核心逻辑:
    - 当前市场价格 vs 估计的真实概率
    - 当 市场价格 < 估计概率 - 安全边际 时产生买入信号
    - 当 市场价格 > 估计概率 + 安全边际 时产生卖出信号

    估计真实概率的方法:
    1. 去除庄家抽水的隐含概率
    2. 多源概率聚合（预测模型、专家预测等）
    3. 历史校准
    """

    def __init__(
        self,
        market_data_source: MarketDataSource,
        event_data_source: Optional[EventDataSource] = None,
        safety_margin: Decimal = Decimal('0.03'),
        min_confidence: Decimal = Decimal('0.6'),
        min_edge: Decimal = Decimal('0.02'),
        probability_estimators: Optional[List[str]] = None
    ):
        """
        初始化赔率偏差信号生成器

        Args:
            market_data_source: 市场数据源
            event_data_source: 事件数据源（可选）
            safety_margin: 安全边际（默认3%）
            min_confidence: 最小置信度
            min_edge: 最小概率优势
            probability_estimators: 概率估计器列表
        """
        super().__init__(
            signal_type=SignalType.ODDS_BIAS,
            min_confidence=min_confidence,
            min_edge=min_edge
        )
        self.market_data_source = market_data_source
        self.event_data_source = event_data_source
        self.safety_margin = safety_margin
        self.probability_estimators = probability_estimators or ['marginal_adjusted']

        logger.info(
            f"OddsBiasSignalGenerator initialized with safety_margin={safety_margin}, "
            f"estimators={self.probability_estimators}"
        )

    async def _estimate_true_probability(
        self,
        market_state: MarketState,
        event_info: Optional[EventInfo] = None
    ) -> Tuple[Decimal, Decimal, str]:
        """
        估计真实概率

        Returns:
            (estimated_probability, confidence, method_used)
        """
        methods_used = []
        estimates = []
        confidences = []

        # 方法1: 去除庄家抽水的隐含概率
        if 'marginal_adjusted' in self.probability_estimators:
            adjusted_prob = calculate_margin_adjusted_probability(
                market_state.yes_price,
                market_state.no_price
            )
            estimates.append(adjusted_prob)
            confidences.append(Decimal('0.7'))
            methods_used.append('marginal_adjusted')

        # 方法2: 基于事件信息的调整
        if event_info and event_info.confidence > 0:
            # 如果有高置信度的外部信息源
            info_prob = Decimal('0.5')  # 默认中性
            if event_info.result == 'yes':
                info_prob = event_info.confidence
            elif event_info.result == 'no':
                info_prob = Decimal('1') - event_info.confidence

            estimates.append(info_prob)
            confidences.append(event_info.confidence)
            methods_used.append('event_info')

        # 方法3: 简单平均（如果没有其他方法）
        if not estimates:
            # 直接使用市场价格作为估计
            estimates.append(market_state.implied_probability)
            confidences.append(Decimal('0.5'))
            methods_used.append('market_implied')

        # 加权平均
        total_weight = sum(confidences)
        weighted_sum = sum(e * c for e, c in zip(estimates, confidences))

        final_estimate = weighted_sum / total_weight if total_weight > 0 else estimates[0]
        final_confidence = min(confidences) if len(confidences) > 1 else confidences[0]

        return (
            min(Decimal('1'), max(Decimal('0'), final_estimate)),
            final_confidence,
            '+'.join(methods_used)
        )

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成赔率偏差信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs:
                - estimated_probability: 外部提供的估计概率
                - external_confidence: 外部估计的置信度

        Returns:
            PolymarketSignal列表
        """
        logger.info(f"Generating odds bias signals for market={market_id}, token={token_id}")

        if not self._check_rate_limit():
            logger.warning("Signal generation rate limit exceeded")
            return []

        signals = []

        try:
            # 获取市场状态
            market_state = await self.market_data_source.get_market_state(
                market_id, token_id
            )

            # 获取事件信息（如果可用）
            event_info = None
            if self.event_data_source and 'event_id' in kwargs:
                try:
                    event_info = await self.event_data_source.get_event_info(
                        kwargs['event_id']
                    )
                except Exception as e:
                    logger.warning(f"Failed to get event info: {e}")

            # 估计真实概率
            external_prob = kwargs.get('estimated_probability')
            if external_prob is not None:
                # 使用外部提供的概率估计
                est_prob = Decimal(str(external_prob))
                confidence = Decimal(str(kwargs.get('external_confidence', '0.8')))
                method = 'external'
            else:
                # 使用内部估计
                est_prob, confidence, method = await self._estimate_true_probability(
                    market_state, event_info
                )

            # 计算边缘
            current_prob = market_state.implied_probability
            edge = est_prob - current_prob

            # 检查是否满足信号条件
            if abs(edge) >= self.min_edge and confidence >= self.min_confidence:
                # 确定方向
                if edge > 0:
                    direction = SignalDirection.BUY
                    reasoning = (
                        f"市场价格({current_prob:.2%})低于估计真实概率({est_prob:.2%})，"
                        f"存在{edge:.2%}的概率优势。估计方法: {method}"
                    )
                else:
                    direction = SignalDirection.SELL
                    reasoning = (
                        f"市场价格({current_prob:.2%})高于估计真实概率({est_prob:.2%})，"
                        f"存在{abs(edge):.2%}的做空优势。估计方法: {method}"
                    )

                # 计算信号强度
                strength = self._calculate_strength(edge, confidence)

                # 计算凯利公式建议
                kelly = calculate_kelly_criterion(abs(edge), market_state.odds_decimal)

                # 创建信号
                signal = PolymarketSignal(
                    signal_id=f"odds_bias_{market_id}_{token_id}_{datetime.utcnow().timestamp()}",
                    timestamp=datetime.utcnow(),
                    market_id=market_id,
                    token_id=token_id,
                    signal_type=SignalType.ODDS_BIAS,
                    direction=direction,
                    strength=strength,
                    current_probability=current_prob,
                    estimated_probability=est_prob,
                    edge=edge,
                    odds=market_state.odds_decimal,
                    confidence=confidence,
                    source_data={
                        'market_state': {
                            'yes_price': float(market_state.yes_price),
                            'no_price': float(market_state.no_price),
                            'volume_24h': float(market_state.volume_24h),
                        },
                        'estimation_method': method,
                    },
                    kelly_fraction=kelly if kelly > 0 else None,
                    reasoning=reasoning,
                    warnings=[] if confidence > Decimal('0.7') else ['置信度较低，建议谨慎']
                )

                signals.append(signal)
                self._record_signal()

                logger.info(
                    f"Generated odds bias signal: direction={direction.name}, "
                    f"edge={edge:.4f}, confidence={confidence:.2f}"
                )
            else:
                logger.debug(
                    f"No signal generated: edge={edge:.4f}, confidence={confidence:.2f}, "
                    f"thresholds: edge>={self.min_edge}, confidence>={self.min_confidence}"
                )

        except Exception as e:
            logger.error(f"Error generating odds bias signal: {e}", exc_info=True)

        return signals


# =============================================================================
# 2. TIME DECAY SIGNAL GENERATOR - 时间衰减信号
# =============================================================================

class TimeDecaySignalGenerator(BaseSignalGenerator):
    """
    时间衰减信号生成器

    核心逻辑:
    - 事件临近时价格向真实结果收敛
    - 时间价值计算：距离事件发生的时间 vs 当前价格
    - 利用时间衰减进行套利

    关键概念:
    - Theta: 时间衰减率
    - Time Value: 时间价值
    - Convergence: 价格向结果收敛
    """

    def __init__(
        self,
        market_data_source: MarketDataSource,
        event_data_source: EventDataSource,
        min_confidence: Decimal = Decimal('0.6'),
        min_edge: Decimal = Decimal('0.02'),
        time_decay_threshold: float = 0.5,
        convergence_threshold: Decimal = Decimal('0.05')
    ):
        """
        初始化时间衰减信号生成器

        Args:
            market_data_source: 市场数据源
            event_data_source: 事件数据源
            min_confidence: 最小置信度
            min_edge: 最小概率优势
            time_decay_threshold: 时间衰减阈值
            convergence_threshold: 价格收敛阈值
        """
        super().__init__(
            signal_type=SignalType.TIME_DECAY,
            min_confidence=min_confidence,
            min_edge=min_edge
        )
        self.market_data_source = market_data_source
        self.event_data_source = event_data_source
        self.time_decay_threshold = time_decay_threshold
        self.convergence_threshold = convergence_threshold

        logger.info(
            f"TimeDecaySignalGenerator initialized with "
            f"decay_threshold={time_decay_threshold}, "
            f"convergence_threshold={convergence_threshold}"
        )

    async def _calculate_time_decay_metrics(
        self,
        market_state: MarketState,
        event_info: EventInfo
    ) -> Dict[str, Any]:
        """
        计算时间衰减相关指标

        Returns:
            包含时间衰减指标的字典
        """
        now = datetime.utcnow()
        hours_to_event = (event_info.expected_resolution - now).total_seconds() / 3600

        # 时间衰减因子
        decay_factor = time_to_event_decay(hours_to_event)

        # 计算理论上的价格收敛目标
        # 假设我们知道结果（实际交易中不会知道）
        # 这里用价格与时间的关系来估计

        # 时间价值（类似于期权theta）
        # 越临近事件，时间价值越低
        time_value = 1 - decay_factor

        # 预期收敛速度
        if hours_to_event > 0:
            # 假设价格会以一定速度向结果收敛
            convergence_speed = decay_factor / math.sqrt(max(1, hours_to_event))
        else:
            convergence_speed = 1.0

        return {
            'hours_to_event': hours_to_event,
            'decay_factor': decay_factor,
            'time_value': time_value,
            'convergence_speed': convergence_speed,
            'event_time': event_info.expected_resolution.isoformat(),
        }

    async def _detect_convergence_opportunities(
        self,
        market_state: MarketState,
        metrics: Dict[str, Any],
        estimated_result_probability: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """
        检测价格收敛机会

        Args:
            market_state: 市场状态
            metrics: 时间衰减指标
            estimated_result_probability: 估计的结果概率（如果已知）

        Returns:
            机会详情或None
        """
        current_prob = market_state.implied_probability
        decay_factor = metrics['decay_factor']
        hours_to_event = metrics['hours_to_event']

        # 如果没有提供估计结果，我们假设价格会向某个"公平价值"收敛
        # 这里简化为假设公平价值是某个固定值或基于历史数据

        if estimated_result_probability is not None:
            # 如果我们知道或估计了结果
            target_prob = estimated_result_probability

            # 计算当前价格到目标价格的距离
            price_distance = abs(target_prob - current_prob)

            # 如果距离足够大且时间足够近，可能存在套利机会
            if price_distance > self.convergence_threshold:
                if decay_factor > self.time_decay_threshold:
                    # 强收敛信号
                    return {
                        'opportunity_type': 'convergence',
                        'target_probability': target_prob,
                        'current_probability': current_prob,
                        'expected_movement': target_prob - current_prob,
                        'confidence': Decimal(str(1 - decay_factor)),
                        'urgency': 'high' if hours_to_event < 24 else 'medium',
                    }
        else:
            # 没有估计结果时，基于时间价值进行交易
            # 临近事件时，时间价值低，可以考虑卖出时间价值
            time_value = metrics['time_value']

            if time_value < 0.2 and hours_to_event < 12:
                # 时间价值很低，可以考虑做多或做空基于其他因素
                return {
                    'opportunity_type': 'low_time_value',
                    'time_value': time_value,
                    'suggested_action': 'consider_directional_bet',
                    'confidence': Decimal('0.5'),
                }

        return None

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成时间衰减信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs:
                - event_id: 事件ID（必需）
                - estimated_result_probability: 估计的结果概率

        Returns:
            PolymarketSignal列表
        """
        logger.info(f"Generating time decay signals for market={market_id}, token={token_id}")

        if not self._check_rate_limit():
            logger.warning("Signal generation rate limit exceeded")
            return []

        signals = []
        event_id = kwargs.get('event_id')

        if not event_id:
            logger.error("event_id is required for time decay signal generation")
            return []

        try:
            # 获取市场状态
            market_state = await self.market_data_source.get_market_state(
                market_id, token_id
            )

            # 获取事件信息
            event_info = await self.event_data_source.get_event_info(event_id)

            # 计算时间衰减指标
            metrics = await self._calculate_time_decay_metrics(market_state, event_info)

            # 检测收敛机会
            opportunity = await self._detect_convergence_opportunities(
                market_state,
                metrics,
                kwargs.get('estimated_result_probability')
            )

            if opportunity:
                # 计算信号参数
                opp_type = opportunity['opportunity_type']

                if opp_type == 'convergence':
                    target_prob = opportunity['target_probability']
                    current_prob = opportunity['current_probability']
                    edge = target_prob - current_prob

                    direction = SignalDirection.BUY if edge > 0 else SignalDirection.SELL
                    confidence = opportunity['confidence']

                    if abs(edge) >= self.min_edge and confidence >= self.min_confidence:
                        strength = self._calculate_strength(edge, confidence)

                        signal = PolymarketSignal(
                            signal_id=f"time_decay_{market_id}_{token_id}_{datetime.utcnow().timestamp()}",
                            timestamp=datetime.utcnow(),
                            market_id=market_id,
                            token_id=token_id,
                            signal_type=SignalType.TIME_DECAY,
                            direction=direction,
                            strength=strength,
                            current_probability=current_prob,
                            estimated_probability=target_prob,
                            edge=edge,
                            odds=market_state.odds_decimal,
                            confidence=confidence,
                            time_horizon_hours=int(metrics['hours_to_event']),
                            source_data={
                                'metrics': metrics,
                                'opportunity': opportunity,
                                'event_info': {
                                    'event_id': event_id,
                                    'expected_resolution': event_info.expected_resolution.isoformat(),
                                }
                            },
                            reasoning=(
                                f"检测到价格收敛机会。当前隐含概率{current_prob:.2%}，"
                                f"估计目标概率{target_prob:.2%}，存在{abs(edge):.2%}的{'做多' if edge > 0 else '做空'}机会。"
                                f"距离事件发生还有{metrics['hours_to_event']:.1f}小时，"
                                f"时间衰减因子为{metrics['decay_factor']:.2f}。"
                            ),
                            warnings=[
                                "时间衰减交易具有较高不确定性" if metrics['hours_to_event'] > 72 else None,
                                "临近事件时流动性可能下降" if metrics['hours_to_event'] < 6 else None,
                            ]
                        )

                        signals.append(signal)
                        self._record_signal()

                        logger.info(
                            f"Generated time decay convergence signal: "
                            f"direction={direction.name}, edge={edge:.4f}"
                        )

                elif opp_type == 'low_time_value':
                    # 低时间价值情况下的信号
                    # 这种情况下通常不生成强信号，只做记录
                    logger.info(
                        f"Low time value detected for {market_id}: "
                        f"time_value={opportunity['time_value']:.2f}"
                    )
            else:
                logger.debug(f"No convergence opportunity detected for {market_id}")

        except Exception as e:
            logger.error(f"Error generating time decay signal: {e}", exc_info=True)

        return signals


# =============================================================================
# 3. ORDERBOOK PRESSURE SIGNAL GENERATOR - 订单簿压力信号
# =============================================================================

class OrderbookPressureSignalGenerator(BaseSignalGenerator):
    """
    订单簿压力信号生成器

    核心逻辑:
    - 买卖盘不平衡检测
    - 大单进场识别（超过鲸鱼阈值的交易）
    - 订单簿深度分析
    - 流动性压力指标

    关键指标:
    - Bid/Ask Imbalance: 买卖盘不平衡度
    - Depth Imbalance: 深度不平衡
    - Whale Activity: 鲸鱼活动检测
    - Pressure Index: 综合压力指数
    """

    def __init__(
        self,
        market_data_source: MarketDataSource,
        whale_threshold_usd: Decimal = Decimal('10000'),
        min_imbalance_ratio: Decimal = Decimal('0.3'),
        depth_levels: int = 5,
        pressure_window_minutes: int = 15,
        min_confidence: Decimal = Decimal('0.6'),
        min_edge: Decimal = Decimal('0.01')
    ):
        """
        初始化订单簿压力信号生成器

        Args:
            market_data_source: 市场数据源
            whale_threshold_usd: 鲸鱼交易阈值（美元）
            min_imbalance_ratio: 最小不平衡比率
            depth_levels: 深度分析层级数
            pressure_window_minutes: 压力计算时间窗口（分钟）
            min_confidence: 最小置信度
            min_edge: 最小概率优势
        """
        super().__init__(
            signal_type=SignalType.ORDERBOOK_PRESSURE,
            min_confidence=min_confidence,
            min_edge=min_edge
        )
        self.market_data_source = market_data_source
        self.whale_threshold_usd = whale_threshold_usd
        self.min_imbalance_ratio = min_imbalance_ratio
        self.depth_levels = depth_levels
        self.pressure_window_minutes = pressure_window_minutes

        # 内部状态跟踪
        self._pressure_history: Dict[str, List[Dict]] = {}

        logger.info(
            f"OrderbookPressureSignalGenerator initialized with "
            f"whale_threshold=${whale_threshold_usd}, "
            f"min_imbalance={min_imbalance_ratio}"
        )

    async def _analyze_orderbook_imbalance(
        self,
        orderbook: OrderBookSnapshot
    ) -> Dict[str, Any]:
        """
        分析订单簿不平衡

        Returns:
            不平衡分析结果
        """
        # 基础不平衡
        basic_imbalance = orderbook.bid_ask_imbalance

        # 深度不平衡（考虑多个层级）
        bid_depth = sum(
            level.size for level in orderbook.bids[:self.depth_levels]
        )
        ask_depth = sum(
            level.size for level in orderbook.asks[:self.depth_levels]
        )

        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            depth_imbalance = (bid_depth - ask_depth) / total_depth
        else:
            depth_imbalance = Decimal('0')

        # 价差分析
        if orderbook.best_bid and orderbook.best_ask:
            spread = orderbook.best_ask.price - orderbook.best_bid.price
            spread_pct = spread / orderbook.mid_price if orderbook.mid_price else Decimal('0')
        else:
            spread = Decimal('0')
            spread_pct = Decimal('0')

        # 综合压力指数 (-1 到 1，正值表示买盘压力)
        pressure_index = (
            float(basic_imbalance) * 0.4 +
            float(depth_imbalance) * 0.4 +
            (1 - min(1, float(spread_pct) * 100)) * 0.2  # 价差越小，压力信号越可靠
        )

        return {
            'basic_imbalance': basic_imbalance,
            'depth_imbalance': depth_imbalance,
            'bid_depth': bid_depth,
            'ask_depth': ask_depth,
            'spread': spread,
            'spread_pct': spread_pct,
            'pressure_index': Decimal(str(pressure_index)),
            'timestamp': datetime.utcnow().isoformat(),
        }

    async def _detect_whales_and_large_orders(
        self,
        recent_trades: List[Trade],
        orderbook: OrderBookSnapshot
    ) -> Dict[str, Any]:
        """
        检测鲸鱼交易和大额订单

        Returns:
            鲸鱼活动分析结果
        """
        # 检测鲸鱼交易
        whale_trades = detect_whales(recent_trades, self.whale_threshold_usd)

        # 分析鲸鱼方向
        whale_buy_volume = sum(
            t.size * t.price for t in whale_trades if t.side == 'buy'
        )
        whale_sell_volume = sum(
            t.size * t.price for t in whale_trades if t.side == 'sell'
        )

        whale_net_flow = whale_buy_volume - whale_sell_volume

        # 检测订单簿中的大额挂单
        large_bids = [
            level for level in orderbook.bids
            if level.size * level.price >= self.whale_threshold_usd
        ]
        large_asks = [
            level for level in orderbook.asks
            if level.size * level.price >= self.whale_threshold_usd
        ]

        # 鲸鱼压力指标
        if whale_buy_volume + whale_sell_volume > 0:
            whale_pressure = (whale_buy_volume - whale_sell_volume) / (whale_buy_volume + whale_sell_volume)
        else:
            whale_pressure = Decimal('0')

        return {
            'whale_trades_count': len(whale_trades),
            'whale_buy_volume': whale_buy_volume,
            'whale_sell_volume': whale_sell_volume,
            'whale_net_flow': whale_net_flow,
            'large_bids_count': len(large_bids),
            'large_asks_count': len(large_asks),
            'whale_pressure': whale_pressure,
            'recent_whale_activity': [
                {
                    'side': t.side,
                    'size': float(t.size),
                    'value_usd': float(t.size * t.price),
                    'timestamp': t.timestamp.isoformat(),
                }
                for t in whale_trades[:5]  # 只取最近5个
            ],
        }

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成订单簿压力信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs:
                - estimated_result_probability: 估计的结果概率

        Returns:
            PolymarketSignal列表
        """
        logger.info(f"Generating orderbook pressure signals for market={market_id}, token={token_id}")

        if not self._check_rate_limit():
            logger.warning("Signal generation rate limit exceeded")
            return []

        signals = []

        try:
            # 获取市场状态
            market_state = await self.market_data_source.get_market_state(
                market_id, token_id
            )

            # 获取订单簿
            orderbook = await self.market_data_source.get_orderbook(
                market_id, token_id, depth=self.depth_levels
            )

            # 获取近期交易
            recent_trades = await self.market_data_source.get_recent_trades(
                market_id, token_id, hours=1
            )

            # 分析订单簿不平衡
            imbalance_analysis = await self._analyze_orderbook_imbalance(orderbook)

            # 检测鲸鱼活动
            whale_analysis = await self._detect_whales_and_large_orders(
                recent_trades, orderbook
            )

            # 计算综合压力指标
            pressure_index = imbalance_analysis['pressure_index']
            whale_pressure = whale_analysis['whale_pressure']

            # 综合压力 (加权平均)
            combined_pressure = (
                float(pressure_index) * 0.6 +
                float(whale_pressure) * 0.4
            )

            # 判断信号
            imbalance_ratio = abs(float(pressure_index))

            if imbalance_ratio >= float(self.min_imbalance_ratio):
                # 确定方向
                if combined_pressure > 0:
                    direction = SignalDirection.BUY
                    edge = Decimal(str(combined_pressure * 0.1))  # 简化的边缘估计
                else:
                    direction = SignalDirection.SELL
                    edge = Decimal(str(-combined_pressure * 0.1))

                # 计算置信度
                confidence = calculate_confidence_score(
                    sample_size=len(recent_trades),
                    edge=abs(edge),
                    time_consistency=1.0 if imbalance_ratio > 0.5 else 0.7,
                    data_quality=0.9
                )

                if abs(edge) >= self.min_edge and confidence >= self.min_confidence:
                    strength = self._calculate_strength(edge, confidence)

                    # 生成信号ID
                    signal_id = f"ob_pressure_{market_id}_{token_id}_{datetime.utcnow().timestamp()}"

                    # 构建推理说明
                    reasoning_parts = []

                    if abs(float(pressure_index)) > 0.5:
                        pressure_desc = "强烈买盘" if float(pressure_index) > 0 else "强烈卖盘"
                        reasoning_parts.append(f"订单簿显示{pressure_desc}压力（不平衡度: {pressure_index:.2f}）")

                    if abs(float(whale_pressure)) > 0.3:
                        whale_desc = "买入" if float(whale_pressure) > 0 else "卖出"
                        reasoning_parts.append(f"检测到鲸鱼{whale_desc}活动（鲸鱼净流向: ${whale_analysis['whale_net_flow']:,.0f}）")

                    reasoning = "; ".join(reasoning_parts)
                    reasoning += f"\n综合压力指数: {combined_pressure:.2f}，估计概率优势: {edge:.2%}"

                    # 风险提示
                    warnings = []
                    if spread_pct := imbalance_analysis.get('spread_pct'):
                        if float(spread_pct) > 0.02:  # 2% spread
                            warnings.append(f"价差较大({float(spread_pct):.2%})，注意滑点风险")

                    if whale_analysis['whale_trades_count'] > 0:
                        warnings.append(f"最近有{whale_analysis['whale_trades_count']}笔鲸鱼交易，注意市场操纵风险")

                    signal = PolymarketSignal(
                        signal_id=signal_id,
                        timestamp=datetime.utcnow(),
                        market_id=market_id,
                        token_id=token_id,
                        signal_type=SignalType.ORDERBOOK_PRESSURE,
                        direction=direction,
                        strength=strength,
                        current_probability=market_state.implied_probability,
                        estimated_probability=market_state.implied_probability + edge,
                        edge=edge,
                        odds=market_state.odds_decimal,
                        confidence=confidence,
                        source_data={
                            'orderbook_analysis': imbalance_analysis,
                            'whale_analysis': whale_analysis,
                            'combined_pressure': combined_pressure,
                            'recent_trades_count': len(recent_trades),
                        },
                        reasoning=reasoning,
                        warnings=warnings,
                    )

                    signals.append(signal)
                    self._record_signal()

                    logger.info(
                        f"Generated orderbook pressure signal: "
                        f"direction={direction.name}, pressure={combined_pressure:.2f}"
                    )
            else:
                logger.debug(
                    f"No significant orderbook pressure detected: "
                    f"imbalance={imbalance_ratio:.2f}, threshold={float(self.min_imbalance_ratio)}"
                )

        except Exception as e:
            logger.error(f"Error generating orderbook pressure signal: {e}", exc_info=True)

        return signals


# =============================================================================
# 4. CAPITAL FLOW SIGNAL GENERATOR - 资金流向信号
# =============================================================================

class CapitalFlowSignalGenerator(BaseSignalGenerator):
    """
    资金流向信号生成器

    核心逻辑:
    - 聪明钱地址跟踪（历史胜率高的账户）
    - 资金净流入/流出分析
    - 鲸鱼活动监控
    - 资金流向与价格背离检测

    聪明钱定义:
    - 历史胜率 > 60%
    - 最少交易次数 > 10
    - 平均盈利 > 平均亏损
    """

    def __init__(
        self,
        market_data_source: MarketDataSource,
        account_data_source: AccountDataSource,
        min_confidence: Decimal = Decimal('0.6'),
        min_edge: Decimal = Decimal('0.02'),
        smart_money_min_win_rate: Decimal = Decimal('0.6'),
        smart_money_min_trades: int = 10,
        flow_window_hours: int = 24,
        whale_threshold_usd: Decimal = Decimal('10000')
    ):
        """
        初始化资金流向信号生成器

        Args:
            market_data_source: 市场数据源
            account_data_source: 账户数据源
            min_confidence: 最小置信度
            min_edge: 最小概率优势
            smart_money_min_win_rate: 聪明钱最小胜率
            smart_money_min_trades: 聪明钱最少交易次数
            flow_window_hours: 资金流向计算窗口（小时）
            whale_threshold_usd: 鲸鱼阈值（美元）
        """
        super().__init__(
            signal_type=SignalType.CAPITAL_FLOW,
            min_confidence=min_confidence,
            min_edge=min_edge
        )
        self.market_data_source = market_data_source
        self.account_data_source = account_data_source
        self.smart_money_min_win_rate = smart_money_min_win_rate
        self.smart_money_min_trades = smart_money_min_trades
        self.flow_window_hours = flow_window_hours
        self.whale_threshold_usd = whale_threshold_usd

        # 聪明钱缓存
        self._smart_money_cache: Optional[List[str]] = None
        self._smart_money_cache_time: Optional[datetime] = None

        logger.info(
            f"CapitalFlowSignalGenerator initialized with "
            f"smart_money_min_win_rate={smart_money_min_win_rate}, "
            f"flow_window={flow_window_hours}h"
        )

    async def _get_smart_money_accounts(self, force_refresh: bool = False) -> List[str]:
        """
        获取聪明钱地址列表（带缓存）
        """
        cache_valid = (
            self._smart_money_cache is not None and
            self._smart_money_cache_time is not None and
            (datetime.utcnow() - self._smart_money_cache_time) < timedelta(hours=1) and
            not force_refresh
        )

        if cache_valid:
            return self._smart_money_cache

        try:
            accounts = await self.account_data_source.get_smart_money_accounts(
                min_win_rate=self.smart_money_min_win_rate,
                min_trades=self.smart_money_min_trades
            )

            self._smart_money_cache = accounts
            self._smart_money_cache_time = datetime.utcnow()

            logger.info(f"Refreshed smart money cache: {len(accounts)} accounts")
            return accounts

        except Exception as e:
            logger.error(f"Failed to get smart money accounts: {e}")
            return self._smart_money_cache or []

    async def _calculate_capital_flow_metrics(
        self,
        market_id: str,
        token_id: str
    ) -> CapitalFlowMetrics:
        """
        计算资金流向指标
        """
        # 获取聪明钱地址
        smart_money = await self._get_smart_money_accounts()

        # 获取近期交易
        all_trades = await self.market_data_source.get_recent_trades(
            market_id, token_id, hours=self.flow_window_hours
        )

        # 计算总流入流出
        total_inflow = sum(
            t.size * t.price for t in all_trades if t.side == 'buy'
        )
        total_outflow = sum(
            t.size * t.price for t in all_trades if t.side == 'sell'
        )

        # 计算聪明钱流入流出
        smart_trades = [t for t in all_trades if t.trader_address in smart_money]

        smart_inflow = sum(
            t.size * t.price for t in smart_trades if t.side == 'buy'
        )
        smart_outflow = sum(
            t.size * t.price for t in smart_trades if t.side == 'sell'
        )

        # 检测鲸鱼交易
        whale_trades = detect_whales(all_trades, self.whale_threshold_usd)

        return CapitalFlowMetrics(
            market_id=market_id,
            period_hours=self.flow_window_hours,
            total_inflow=total_inflow,
            total_outflow=total_outflow,
            net_flow=total_inflow - total_outflow,
            smart_money_inflow=smart_inflow,
            smart_money_outflow=smart_outflow,
            whale_trades=whale_trades,
            timestamp=datetime.utcnow()
        )

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成资金流向信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs:
                - smart_money_override: 强制使用指定的聪明钱列表

        Returns:
            PolymarketSignal列表
        """
        logger.info(f"Generating capital flow signals for market={market_id}, token={token_id}")

        if not self._check_rate_limit():
            logger.warning("Signal generation rate limit exceeded")
            return []

        signals = []

        try:
            # 获取市场状态
            market_state = await self.market_data_source.get_market_state(
                market_id, token_id
            )

            # 计算资金流向指标
            flow_metrics = await self._calculate_capital_flow_metrics(
                market_id, token_id
            )

            # 分析聪明钱流向
            smart_net_flow = flow_metrics.smart_money_inflow - flow_metrics.smart_money_outflow
            total_smart_volume = flow_metrics.smart_money_inflow + flow_metrics.smart_money_outflow

            # 聪明钱流向比率
            if total_smart_volume > 0:
                smart_flow_ratio = smart_net_flow / total_smart_volume
            else:
                smart_flow_ratio = Decimal('0')

            # 分析鲸鱼活动
            whale_buy_value = sum(
                t.size * t.price for t in flow_metrics.whale_trades if t.side == 'buy'
            )
            whale_sell_value = sum(
                t.size * t.price for t in flow_metrics.whale_trades if t.side == 'sell'
            )

            whale_net = whale_buy_value - whale_sell_value
            total_whale = whale_buy_value + whale_sell_value

            if total_whale > 0:
                whale_ratio = whale_net / total_whale
            else:
                whale_ratio = Decimal('0')

            # 综合资金流向信号
            # 权重: 聪明钱 50%, 鲸鱼 30%, 总体资金流向 20%
            combined_flow = (
                float(smart_flow_ratio) * 0.5 +
                float(whale_ratio) * 0.3 +
                float(flow_metrics.net_flow) / float(flow_metrics.total_inflow + flow_metrics.total_outflow + 1) * 0.2
            )

            # 判断信号条件
            flow_threshold = 0.3  # 30%的净流向阈值

            if abs(combined_flow) >= flow_threshold:
                # 确定方向
                if combined_flow > 0:
                    direction = SignalDirection.BUY
                    edge = Decimal(str(combined_flow * 0.05))  # 简化的边缘估计
                else:
                    direction = SignalDirection.SELL
                    edge = Decimal(str(combined_flow * 0.05))

                # 计算置信度
                confidence_factors = []

                # 聪明钱活跃度
                if total_smart_volume > self.whale_threshold_usd * 5:
                    confidence_factors.append(0.8)
                else:
                    confidence_factors.append(0.5)

                # 鲸鱼活动
                if len(flow_metrics.whale_trades) >= 3:
                    confidence_factors.append(0.9)
                elif len(flow_metrics.whale_trades) >= 1:
                    confidence_factors.append(0.7)
                else:
                    confidence_factors.append(0.4)

                # 流向一致性
                flow_consistency = 1.0 if float(smart_flow_ratio) * float(whale_ratio) > 0 else 0.5
                confidence_factors.append(flow_consistency)

                confidence = Decimal(str(sum(confidence_factors) / len(confidence_factors)))

                if abs(edge) >= self.min_edge and confidence >= self.min_confidence:
                    strength = self._calculate_strength(edge, confidence)

                    signal_id = f"capital_flow_{market_id}_{token_id}_{datetime.utcnow().timestamp()}"

                    # 构建推理说明
                    flow_direction = "流入" if combined_flow > 0 else "流出"
                    reasoning = (
                        f"检测到显著的聪明钱和鲸鱼资金{flow_direction}。"
                        f"聪明钱净流向: ${smart_net_flow:,.0f} ({smart_flow_ratio:.1%})，"
                        f"鲸鱼净流向: ${whale_net:,.0f} ({whale_ratio:.1%})。"
                        f"综合资金流向指标: {combined_flow:.2f}。"
                        f"过去{self.flow_window_hours}小时内共有{len(flow_metrics.whale_trades)}笔鲸鱼交易。"
                    )

                    # 风险提示
                    warnings = []
                    if float(confidence) < 0.7:
                        warnings.append("资金流向信号置信度较低")
                    if abs(combined_flow) < 0.5:
                        warnings.append("资金流向强度一般，建议谨慎")
                    if len(flow_metrics.whale_trades) == 0:
                        warnings.append("近期无鲸鱼活动，信号可靠性存疑")

                    signal = PolymarketSignal(
                        signal_id=signal_id,
                        timestamp=datetime.utcnow(),
                        market_id=market_id,
                        token_id=token_id,
                        signal_type=SignalType.CAPITAL_FLOW,
                        direction=direction,
                        strength=strength,
                        current_probability=market_state.implied_probability,
                        estimated_probability=market_state.implied_probability + edge,
                        edge=edge,
                        odds=market_state.odds_decimal,
                        confidence=confidence,
                        source_data={
                            'flow_metrics': {
                                'total_inflow': float(flow_metrics.total_inflow),
                                'total_outflow': float(flow_metrics.total_outflow),
                                'net_flow': float(flow_metrics.net_flow),
                                'smart_money_inflow': float(flow_metrics.smart_money_inflow),
                                'smart_money_outflow': float(flow_metrics.smart_money_outflow),
                                'whale_trades_count': len(flow_metrics.whale_trades),
                            },
                            'flow_analysis': {
                                'smart_flow_ratio': float(smart_flow_ratio),
                                'whale_ratio': float(whale_ratio),
                                'combined_flow': combined_flow,
                            }
                        },
                        reasoning=reasoning,
                        warnings=warnings,
                    )

                    signals.append(signal)
                    self._record_signal()

                    logger.info(
                        f"Generated capital flow signal: "
                        f"direction={direction.name}, flow={combined_flow:.2f}, "
                        f"confidence={confidence:.2f}"
                    )
            else:
                logger.debug(
                    f"No significant capital flow signal: "
                    f"combined_flow={combined_flow:.2f}, threshold={flow_threshold}"
                )

        except Exception as e:
            logger.error(f"Error generating capital flow signal: {e}", exc_info=True)

        return signals


# =============================================================================
# 5. INFORMATION EDGE SIGNAL GENERATOR - 信息优势信号
# =============================================================================

class InformationEdgeSignalGenerator(BaseSignalGenerator):
    """
    信息优势信号生成器

    核心逻辑:
    - 新闻/事件对价格的冲击
    - 提前结果检测（体育比赛已结束但市场未结算）
    - 社交媒体情绪分析（如果可用）
    - 链上数据异常检测

    信息优势类型:
    1. Early Result Detection: 提前结果检测
    2. News Impact: 新闻冲击
    3. Insider Activity: 内幕活动检测
    4. Cross-Market Arbitrage: 跨市场信息套利
    """

    def __init__(
        self,
        market_data_source: MarketDataSource,
        event_data_source: EventDataSource,
        account_data_source: Optional[AccountDataSource] = None,
        min_confidence: Decimal = Decimal('0.7'),  # 信息优势需要更高置信度
        min_edge: Decimal = Decimal('0.03'),
        early_result_threshold: Decimal = Decimal('0.95'),
        news_impact_window_minutes: int = 30
    ):
        """
        初始化信息优势信号生成器

        Args:
            market_data_source: 市场数据源
            event_data_source: 事件数据源
            account_data_source: 账户数据源（可选）
            min_confidence: 最小置信度（信息优势信号通常需要更高置信度）
            min_edge: 最小概率优势
            early_result_threshold: 提前结果检测阈值
            news_impact_window_minutes: 新闻影响评估窗口
        """
        super().__init__(
            signal_type=SignalType.INFORMATION_EDGE,
            min_confidence=min_confidence,
            min_edge=min_edge
        )
        self.market_data_source = market_data_source
        self.event_data_source = event_data_source
        self.account_data_source = account_data_source
        self.early_result_threshold = early_result_threshold
        self.news_impact_window_minutes = news_impact_window_minutes

        # 检测结果缓存
        self._early_result_cache: Dict[str, Tuple[bool, Optional[str], datetime]] = {}

        logger.info(
            f"InformationEdgeSignalGenerator initialized with "
            f"early_result_threshold={early_result_threshold}"
        )

    async def _check_early_result(
        self,
        event_id: str
    ) -> Tuple[bool, Optional[str], Decimal]:
        """
        检查是否有提前可获得的结果

        Returns:
            (has_early_result, result_value, confidence)
        """
        # 检查缓存
        if event_id in self._early_result_cache:
            cached_result, cached_time = self._early_result_cache[event_id][1], self._early_result_cache[event_id][2]
            if datetime.utcnow() - cached_time < timedelta(minutes=5):
                return (
                    self._early_result_cache[event_id][0],
                    cached_result,
                    Decimal('0.95')
                )

        try:
            # 调用事件数据源检查结果可用性
            is_available, result = await self.event_data_source.check_result_availability(event_id)

            confidence = Decimal('0.95') if is_available else Decimal('0.3')

            # 更新缓存
            self._early_result_cache[event_id] = (is_available, result, datetime.utcnow())

            return is_available, result, confidence

        except Exception as e:
            logger.warning(f"Failed to check early result for {event_id}: {e}")
            return False, None, Decimal('0.3')

    async def _analyze_recent_trades_for_insider_activity(
        self,
        trades: List[Trade],
        smart_money: List[str]
    ) -> Dict[str, Any]:
        """
        分析近期交易中的潜在内幕活动

        Returns:
            内幕活动分析结果
        """
        # 按交易者分组
        trader_activity: Dict[str, Dict] = {}

        for trade in trades:
            if not trade.trader_address:
                continue

            if trade.trader_address not in trader_activity:
                trader_activity[trade.trader_address] = {
                    'buy_volume': Decimal('0'),
                    'sell_volume': Decimal('0'),
                    'trade_count': 0,
                    'is_smart_money': trade.trader_address in smart_money,
                }

            volume = trade.size * trade.price
            if trade.side == 'buy':
                trader_activity[trade.trader_address]['buy_volume'] += volume
            else:
                trader_activity[trade.trader_address]['sell_volume'] += volume

            trader_activity[trade.trader_address]['trade_count'] += 1

        # 检测异常活动（潜在内幕）
        suspicious_activity = []

        for address, activity in trader_activity.items():
            total_volume = activity['buy_volume'] + activity['sell_volume']
            net_flow = activity['buy_volume'] - activity['sell_volume']

            # 检测大额单边交易（可能知道内幕）
            if total_volume > self.whale_threshold_usd * 2:
                if abs(net_flow) > total_volume * Decimal('0.8'):  # 90%以上是单边
                    suspicious_activity.append({
                        'address': address,
                        'type': 'large_unidirectional',
                        'total_volume': total_volume,
                        'net_flow': net_flow,
                        'is_smart_money': activity['is_smart_money'],
                        'confidence_boost': Decimal('0.2') if activity['is_smart_money'] else Decimal('0.1'),
                    })

        # 统计聪明钱整体流向
        smart_money_buy = sum(
            a['buy_volume'] for addr, a in trader_activity.items()
            if a['is_smart_money']
        )
        smart_money_sell = sum(
            a['sell_volume'] for addr, a in trader_activity.items()
            if a['is_smart_money']
        )

        return {
            'trader_count': len(trader_activity),
            'smart_money_count': sum(1 for a in trader_activity.values() if a['is_smart_money']),
            'suspicious_activity': suspicious_activity,
            'smart_money_buy_volume': smart_money_buy,
            'smart_money_sell_volume': smart_money_sell,
            'smart_money_net': smart_money_buy - smart_money_sell,
        }

    async def generate_signals(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> List[PolymarketSignal]:
        """
        生成信息优势信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs:
                - event_id: 事件ID

        Returns:
            PolymarketSignal列表
        """
        logger.info(f"Generating information edge signals for market={market_id}, token={token_id}")

        if not self._check_rate_limit():
            logger.warning("Signal generation rate limit exceeded")
            return []

        signals = []
        event_id = kwargs.get('event_id')

        try:
            # 获取市场状态
            market_state = await self.market_data_source.get_market_state(
                market_id, token_id
            )

            current_prob = market_state.implied_probability

            # 1. 检查提前结果
            early_result_confidence = Decimal('0')
            early_result_value = None

            if event_id:
                has_early, result, confidence = await self._check_early_result(event_id)
                if has_early and result:
                    early_result_confidence = confidence
                    early_result_value = result

            # 2. 分析聪明钱和资金流向
            smart_money = await self._get_smart_money_accounts()
            recent_trades = await self.market_data_source.get_recent_trades(
                market_id, token_id, hours=self.flow_window_hours
            )

            insider_analysis = await self._analyze_recent_trades_for_insider_activity(
                recent_trades, smart_money
            )

            # 3. 综合评估信息优势
            info_signals = []

            # 提前结果信号（最高优先级）
            if early_result_value and early_result_confidence >= self.early_result_threshold:
                if early_result_value.lower() == 'yes':
                    target_prob = Decimal('0.95')
                elif early_result_value.lower() == 'no':
                    target_prob = Decimal('0.05')
                else:
                    target_prob = current_prob

                edge = target_prob - current_prob

                if abs(edge) >= self.min_edge:
                    info_signals.append({
                        'type': 'early_result',
                        'direction': SignalDirection.BUY if edge > 0 else SignalDirection.SELL,
                        'edge': edge,
                        'confidence': early_result_confidence,
                        'reasoning': f"检测到提前可获得的结果: {early_result_value}，置信度{early_result_confidence:.1%}",
                    })

            # 聪明钱共识信号
            smart_net = insider_analysis.get('smart_money_net', Decimal('0'))
            smart_buy = insider_analysis.get('smart_money_buy_volume', Decimal('0'))
            smart_sell = insider_analysis.get('smart_money_sell_volume', Decimal('0'))
            smart_total = smart_buy + smart_sell

            if smart_total > 0:
                smart_ratio = smart_net / smart_total

                # 聪明钱强烈共识（>60%一致性）
                if abs(float(smart_ratio)) >= 0.6 and smart_total >= self.whale_threshold_usd:
                    smart_edge = Decimal(str(smart_ratio * 0.05))  # 5% max edge from smart money

                    info_signals.append({
                        'type': 'smart_money_consensus',
                        'direction': SignalDirection.BUY if smart_ratio > 0 else SignalDirection.SELL,
                        'edge': smart_edge,
                        'confidence': Decimal(str(min(0.9, 0.6 + abs(float(smart_ratio)) * 0.3))),
                        'reasoning': (
                            f"聪明钱显示强烈{'看涨' if smart_ratio > 0 else '看跌'}共识，"
                            f"{insider_analysis.get('smart_money_count', 0)}个聪明钱地址"
                            f"净{ '买入' if smart_ratio > 0 else '卖出' }${abs(smart_net):,.0f}"
                        ),
                    })

            # 内幕活动检测
            suspicious = insider_analysis.get('suspicious_activity', [])
            for activity in suspicious:
                if activity.get('confidence_boost', Decimal('0')) >= Decimal('0.15'):
                    # 检测到高置信度可疑活动
                    direction = SignalDirection.BUY if activity['net_flow'] > 0 else SignalDirection.SELL
                    edge = Decimal('0.08') if activity.get('is_smart_money') else Decimal('0.04')

                    info_signals.append({
                        'type': 'suspicious_activity',
                        'direction': direction,
                        'edge': edge,
                        'confidence': Decimal('0.75') if activity.get('is_smart_money') else Decimal('0.6'),
                        'reasoning': (
                            f"检测到可疑的大额单边交易活动，"
                            f"地址{activity['address'][:10]}..."
                            f"在{self.flow_window_hours}小时内"
                            f"{'买入' if activity['net_flow'] > 0 else '卖出'}"
                            f"${abs(activity['net_flow']):,.0f}"
                            f"({'聪明钱' if activity.get('is_smart_money') else '普通用户'})"
                        ),
                    })

            # 为每个检测到的信号创建PolymarketSignal
            for info_signal in info_signals:
                edge = info_signal['edge']
                confidence = info_signal['confidence']

                if abs(edge) < self.min_edge or confidence < self.min_confidence:
                    continue

                direction = info_signal['direction']
                strength = self._calculate_strength(edge, confidence)

                signal_id = (
                    f"info_edge_{info_signal['type']}_{market_id}_{token_id}_"
                    f"{datetime.utcnow().timestamp()}"
                )

                # 计算估计概率
                if direction == SignalDirection.BUY:
                    estimated_prob = min(Decimal('0.95'), current_prob + edge)
                else:
                    estimated_prob = max(Decimal('0.05'), current_prob - edge)

                # 风险提示
                warnings = []
                if info_signal['type'] == 'suspicious_activity':
                    warnings.append("基于可疑交易活动，可能存在监管风险")
                if info_signal['type'] == 'early_result':
                    warnings.append("提前结果可能因数据延迟而不准确")
                if confidence < Decimal('0.75'):
                    warnings.append("信息优势信号置信度较低，建议验证")

                signal = PolymarketSignal(
                    signal_id=signal_id,
                    timestamp=datetime.utcnow(),
                    market_id=market_id,
                    token_id=token_id,
                    signal_type=SignalType.INFORMATION_EDGE,
                    direction=direction,
                    strength=strength,
                    current_probability=current_prob,
                    estimated_probability=estimated_prob,
                    edge=edge,
                    odds=market_state.odds_decimal,
                    confidence=confidence,
                    source_data={
                        'signal_subtype': info_signal['type'],
                        'insider_analysis': {
                            'smart_money_count': insider_analysis.get('smart_money_count', 0),
                            'suspicious_activities': len([s for s in info_signals if s['type'] == 'suspicious_activity']),
                        },
                        'early_result': {
                            'available': early_result_value is not None,
                            'value': early_result_value,
                            'confidence': float(early_result_confidence),
                        } if early_result_value else None,
                    },
                    reasoning=info_signal['reasoning'],
                    warnings=warnings,
                )

                signals.append(signal)
                self._record_signal()

                logger.info(
                    f"Generated information edge signal: "
                    f"type={info_signal['type']}, direction={direction.name}, "
                    f"confidence={confidence:.2f}"
                )

        except Exception as e:
            logger.error(f"Error generating information edge signal: {e}", exc_info=True)

        return signals


# =============================================================================
# COMPOUND SIGNAL GENERATOR - 复合信号生成器（可选）
# =============================================================================

class CompoundSignalGenerator:
    """
    复合信号生成器

    整合多个信号生成器的结果，生成综合信号。
    可用于信号确认和增强。
    """

    def __init__(
        self,
        generators: List[BaseSignalGenerator],
        min_agreement_ratio: float = 0.6,
        min_composite_confidence: Decimal = Decimal('0.65')
    ):
        """
        初始化复合信号生成器

        Args:
            generators: 基础信号生成器列表
            min_agreement_ratio: 最小一致率（多少生成器需要同意）
            min_composite_confidence: 最小复合置信度
        """
        self.generators = generators
        self.min_agreement_ratio = min_agreement_ratio
        self.min_composite_confidence = min_composite_confidence

        logger.info(
            f"CompoundSignalGenerator initialized with {len(generators)} generators"
        )

    async def generate_composite_signal(
        self,
        market_id: str,
        token_id: str,
        **kwargs
    ) -> Optional[PolymarketSignal]:
        """
        生成复合信号

        Args:
            market_id: 市场ID
            token_id: Token ID
            **kwargs: 传递给基础生成器的参数

        Returns:
            复合PolymarketSignal或None
        """
        logger.info(f"Generating composite signal for market={market_id}, token={token_id}")

        # 收集所有生成器的信号
        all_signals: List[PolymarketSignal] = []

        for generator in self.generators:
            try:
                signals = await generator.generate_signals(
                    market_id, token_id, **kwargs
                )
                all_signals.extend(signals)
            except Exception as e:
                logger.error(f"Error in generator {generator.__class__.__name__}: {e}")

        if not all_signals:
            logger.debug("No signals from any generator")
            return None

        # 分析信号一致性
        buy_signals = [s for s in all_signals if s.direction == SignalDirection.BUY]
        sell_signals = [s for s in all_signals if s.direction == SignalDirection.SELL]

        total_signals = len(all_signals)
        buy_ratio = len(buy_signals) / total_signals if total_signals > 0 else 0
        sell_ratio = len(sell_signals) / total_signals if total_signals > 0 else 0

        # 检查是否满足一致率要求
        consensus_direction = None
        consensus_signals = []

        if buy_ratio >= self.min_agreement_ratio:
            consensus_direction = SignalDirection.BUY
            consensus_signals = buy_signals
        elif sell_ratio >= self.min_agreement_ratio:
            consensus_direction = SignalDirection.SELL
            consensus_signals = sell_signals

        if not consensus_direction:
            logger.debug(
                f"No consensus reached: buy_ratio={buy_ratio:.2f}, "
                f"sell_ratio={sell_ratio:.2f}, required={self.min_agreement_ratio}"
            )
            return None

        # 计算复合信号参数
        avg_edge = sum(s.edge for s in consensus_signals) / len(consensus_signals)
        avg_confidence = sum(s.confidence for s in consensus_signals) / len(consensus_signals)

        # 复合置信度提升
        composite_confidence = min(
            Decimal('0.98'),
            avg_confidence * Decimal(str(1 + (len(consensus_signals) - 1) * 0.1))
        )

        if composite_confidence < self.min_composite_confidence:
            logger.debug(f"Composite confidence too low: {composite_confidence:.2f}")
            return None

        # 获取参考市场状态（从第一个信号）
        ref_signal = consensus_signals[0]

        # 生成复合信号
        signal_id = f"compound_{market_id}_{token_id}_{datetime.utcnow().timestamp()}"

        strength = self._calculate_strength(avg_edge, composite_confidence)

        # 构建推理说明
        source_types = list(set(s.signal_type.value for s in consensus_signals))
        reasoning = (
            f"复合信号（基于{len(consensus_signals)}个{consensus_direction.name}信号）。\n"
            f"信号来源类型: {', '.join(source_types)}。\n"
            f"一致率: {len(consensus_signals)/total_signals:.1%} ({len(consensus_signals)}/{total_signals})。\n"
            f"平均概率优势: {avg_edge:.2%}，复合置信度: {composite_confidence:.1%}。"
        )

        signal = PolymarketSignal(
            signal_id=signal_id,
            timestamp=datetime.utcnow(),
            market_id=market_id,
            token_id=token_id,
            signal_type=SignalType.COMPOUND,
            direction=consensus_direction,
            strength=strength,
            current_probability=ref_signal.current_probability,
            estimated_probability=ref_signal.current_probability + avg_edge,
            edge=avg_edge,
            odds=ref_signal.odds,
            confidence=composite_confidence,
            source_data={
                'component_signals': [
                    {
                        'signal_id': s.signal_id,
                        'signal_type': s.signal_type.value,
                        'edge': float(s.edge),
                        'confidence': float(s.confidence),
                    }
                    for s in consensus_signals
                ],
                'consensus_stats': {
                    'total_signals': total_signals,
                    'consensus_count': len(consensus_signals),
                    'agreement_ratio': len(consensus_signals) / total_signals if total_signals > 0 else 0,
                    'avg_edge': float(avg_edge),
                    'avg_confidence': float(avg_confidence),
                }
            },
            reasoning=reasoning,
            warnings=[
                "复合信号虽然经过多重确认，但仍可能受系统性偏差影响",
                "建议结合基本面分析进行最终决策",
            ] if composite_confidence < Decimal('0.85') else [],
        )

        signals.append(signal)
        self._record_signal()

        logger.info(
            f"Generated compound signal: direction={consensus_direction.name}, "
            f"components={len(consensus_signals)}, confidence={composite_confidence:.2f}"
        )

        return signals


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'SignalType',
    'SignalStrength',
    'SignalDirection',

    # Data Classes
    'MarketState',
    'OrderBookLevel',
    'OrderBookSnapshot',
    'Trade',
    'CapitalFlowMetrics',
    'EventInfo',
    'PolymarketSignal',

    # Protocols
    'MarketDataSource',
    'EventDataSource',
    'AccountDataSource',

    # Helper Functions
    'calculate_kelly_criterion',
    'calculate_expected_value',
    'time_to_event_decay',
    'calculate_implied_probability',
    'calculate_margin_adjusted_probability',
    'detect_whales',
    'calculate_confidence_score',

    # Signal Generators
    'BaseSignalGenerator',
    'OddsBiasSignalGenerator',
    'TimeDecaySignalGenerator',
    'OrderbookPressureSignalGenerator',
    'CapitalFlowSignalGenerator',
    'InformationEdgeSignalGenerator',
    'CompoundSignalGenerator',
]