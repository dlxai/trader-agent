"""
Signal Generator Module - Polymarket专用信号生成器

本模块提供预测市场专用的信号生成能力，完全移除传统股票技术指标，
使用针对Polymarket等预测市场设计的专用信号。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Union
import json

import aiohttp
import asyncio


logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型枚举"""
    ODDS_BIAS = "odds_bias"           # 赔率偏向
    TIME_DECAY = "time_decay"         # 时间衰减
    ORDERBOOK_PRESSURE = "orderbook_pressure"  # 订单簿压力
    CAPITAL_FLOW = "capital_flow"     # 资金流向
    INFORMATION_EDGE = "information_edge"  # 信息优势
    COMPOUND = "compound"             # 复合信号


class SignalDirection(Enum):
    """信号方向"""
    BULLISH = "bullish"      # 看涨/看多
    BEARISH = "bearish"      # 看跌/看空
    NEUTRAL = "neutral"      # 中性


@dataclass
class Signal:
    """信号数据类"""
    type: SignalType
    direction: SignalDirection
    confidence: float  # 0-1之间的置信度
    strength: float   # 信号强度，可以是任意数值
    timestamp: datetime
    market_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证信号数据"""
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "strength": self.strength,
            "timestamp": self.timestamp.isoformat(),
            "market_id": self.market_id,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """从字典创建信号"""
        return cls(
            type=SignalType(data["type"]),
            direction=SignalDirection(data["direction"]),
            confidence=data["confidence"],
            strength=data["strength"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            market_id=data["market_id"],
            metadata=data.get("metadata", {})
        )


class SignalGenerator(ABC):
    """信号生成器抽象基类"""

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        self.proxy_url = proxy_url
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成交易信号

        Args:
            market_data: 市场数据字典

        Returns:
            Signal: 交易信号
        """
        pass

    async def _fetch_data(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        通过代理获取数据

        Args:
            url: 请求URL
            headers: 请求头

        Returns:
            Dict: 响应数据
        """
        try:
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=self.proxy_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            self.logger.error(f"Error fetching data from {url}: {e}")
            raise


class OddsBiasSignalGenerator(SignalGenerator):
    """
    赔率偏向信号生成器

    检测市场赔率是否偏离真实概率，识别市场偏向（过度乐观/悲观）
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.bias_history: List[Dict[str, Any]] = []

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成赔率偏向信号

        Args:
            market_data: 包含以下字段:
                - market_id: 市场ID
                - yes_price: Yes期权价格 (0-1)
                - no_price: No期权价格 (0-1)
                - implied_probability: 隐含概率
                - real_probability: 真实概率估计 (可选)
                - volume: 交易量

        Returns:
            Signal: 赔率偏向信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")
            yes_price = market_data.get("yes_price", 0.5)
            no_price = market_data.get("no_price", 0.5)
            implied_prob = market_data.get("implied_probability", yes_price)
            real_prob = market_data.get("real_probability")
            volume = market_data.get("volume", 0)

            # 计算隐含概率偏差
            if real_prob is not None:
                prob_bias = implied_prob - real_prob
            else:
                # 使用历史数据估算真实概率
                prob_bias = self._estimate_probability_bias(market_id, implied_prob)

            # 计算赔率偏离度
            fair_price = real_prob if real_prob else implied_prob - prob_bias
            price_deviation = (yes_price - fair_price) / fair_price if fair_price > 0 else 0

            # 计算市场偏向强度
            bias_strength = abs(prob_bias) * volume / 1000  # 归一化

            # 确定信号方向
            if prob_bias > 0.05:  # 隐含概率过高（市场过度乐观）
                direction = SignalDirection.BEARISH  # 看空 - 价格可能下跌
                confidence = min(abs(prob_bias) * 2, 1.0)
            elif prob_bias < -0.05:  # 隐含概率过低（市场过度悲观）
                direction = SignalDirection.BULLISH  # 看多 - 价格可能上涨
                confidence = min(abs(prob_bias) * 2, 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5

            # 记录偏差历史
            self.bias_history.append({
                "timestamp": datetime.now(),
                "market_id": market_id,
                "prob_bias": prob_bias,
                "price_deviation": price_deviation
            })

            # 保持历史记录在合理范围
            if len(self.bias_history) > 1000:
                self.bias_history = self.bias_history[-500:]

            signal = Signal(
                type=SignalType.ODDS_BIAS,
                direction=direction,
                confidence=confidence,
                strength=bias_strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "implied_probability": implied_prob,
                    "real_probability": real_prob,
                    "probability_bias": prob_bias,
                    "price_deviation": price_deviation,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "volume": volume
                }
            )

            self.logger.info(
                f"OddsBias signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, bias={prob_bias:.3f}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating odds bias signal: {e}")
            raise

    def _estimate_probability_bias(self, market_id: str, current_implied_prob: float) -> float:
        """
        基于历史数据估算概率偏差

        Args:
            market_id: 市场ID
            current_implied_prob: 当前隐含概率

        Returns:
            float: 估算的概率偏差
        """
        # 过滤该市场的历史记录
        market_history = [
            h for h in self.bias_history
            if h["market_id"] == market_id
        ]

        if len(market_history) < 5:
            # 数据不足，假设无偏差
            return 0.0

        # 计算历史偏差的中位数（更稳健）
        biases = [h["prob_bias"] for h in market_history[-20:]]  # 最近20个
        biases.sort()
        median_bias = biases[len(biases) // 2]

        # 结合当前隐含概率调整
        # 如果隐含概率接近0或1，通常存在偏差
        edge_penalty = 0.0
        if current_implied_prob < 0.1:
            edge_penalty = 0.05 * (0.1 - current_implied_prob) / 0.1
        elif current_implied_prob > 0.9:
            edge_penalty = -0.05 * (current_implied_prob - 0.9) / 0.1

        return median_bias + edge_penalty


class TimeDecaySignalGenerator(SignalGenerator):
    """
    时间衰减信号生成器

    基于预测市场临近到期时的价值衰减模型，
    分析时间价值和波动率微笑/偏斜。
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.decay_model_cache: Dict[str, Any] = {}

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成时间衰减信号

        Args:
            market_data: 包含以下字段:
                - market_id: 市场ID
                - expiration_date: 到期日期 (ISO格式)
                - current_price: 当前价格
                - strike_price: 行权价 (对于二元期权通常为1)
                - volatility: 隐含波动率
                - volume: 交易量
                - open_interest: 未平仓合约

        Returns:
            Signal: 时间衰减信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")
            expiration_str = market_data.get("expiration_date")
            current_price = market_data.get("current_price", 0.5)
            volatility = market_data.get("volatility", 0.5)
            volume = market_data.get("volume", 0)
            open_interest = market_data.get("open_interest", 0)

            # 解析到期日期
            if expiration_str:
                expiration_date = datetime.fromisoformat(expiration_str.replace('Z', '+00:00'))
                time_to_expiration = (expiration_date - datetime.now(expiration_date.tzinfo)).total_seconds() / 86400  # 天数
            else:
                time_to_expiration = 30  # 默认值

            # 计算时间衰减 (Theta)
            theta = self._calculate_theta(
                current_price,
                time_to_expiration,
                volatility
            )

            # 计算波动率微笑/偏斜
            skew = self._calculate_volatility_skew(
                market_id,
                current_price,
                volatility,
                market_data.get("option_chain", {})
            )

            # 计算Gamma (价格加速度)
            gamma = self._calculate_gamma(
                current_price,
                time_to_expiration,
                volatility
            )

            # 计算时间价值占比
            time_value_ratio = self._calculate_time_value_ratio(
                current_price,
                time_to_expiration,
                market_data.get("intrinsic_value", current_price)
            )

            # 确定信号方向
            # 时间衰减通常对期权买方不利，但可用于策略性入场时机
            if theta < -0.05 and time_to_expiration < 7:
                # 临近到期的高衰减 - 可能是快速套利机会或风险警示
                if gamma > 0.1:
                    direction = SignalDirection.BULLISH if current_price > 0.5 else SignalDirection.BEARISH
                    confidence = min(abs(gamma) * 5, 1.0)
                else:
                    direction = SignalDirection.NEUTRAL
                    confidence = 0.5
            elif skew > 0.2:
                # 波动率偏斜显示下行风险担忧
                direction = SignalDirection.BEARISH
                confidence = min(skew, 1.0)
            elif skew < -0.2:
                # 波动率偏斜显示上行潜力
                direction = SignalDirection.BULLISH
                confidence = min(abs(skew), 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5

            # 计算信号强度
            strength = abs(theta) * 10 + abs(gamma) * 5 + abs(skew) * 3

            signal = Signal(
                type=SignalType.TIME_DECAY,
                direction=direction,
                confidence=confidence,
                strength=strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "time_to_expiration_days": time_to_expiration,
                    "theta": theta,
                    "gamma": gamma,
                    "volatility_skew": skew,
                    "time_value_ratio": time_value_ratio,
                    "current_price": current_price,
                    "volatility": volatility,
                    "volume": volume,
                    "open_interest": open_interest
                }
            )

            self.logger.info(
                f"TimeDecay signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, theta={theta:.4f}, "
                f"time_to_exp={time_to_expiration:.1f}days"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating time decay signal: {e}")
            raise

    def _calculate_theta(self, price: float, time_to_exp: float, volatility: float) -> float:
        """
        计算时间衰减 (Theta)

        对于二元期权，时间衰减在接近到期时加速
        """
        if time_to_exp <= 0:
            return 0.0

        # 简化模型：时间衰减与剩余时间的平方根成反比
        # 且在价格接近0.5时最大
        time_factor = 1.0 / (2 * (time_to_exp ** 0.5))
        price_factor = 1.0 - abs(price - 0.5) * 2  # 在0.5时最大，在0或1时为0
        volatility_factor = volatility / 0.5  # 波动率归一化

        theta = -time_factor * price_factor * volatility_factor
        return theta

    def _calculate_gamma(self, price: float, time_to_exp: float, volatility: float) -> float:
        """
        计算Gamma (价格变化加速度)

        Gamma在价格接近0.5且临近到期时最大
        """
        if time_to_exp <= 0:
            return 0.0

        price_distance = abs(price - 0.5)
        gamma = (1.0 / (time_to_exp ** 0.5 + 0.1)) * (1.0 - price_distance * 2)
        gamma *= volatility * 2

        return max(0, gamma)

    def _calculate_volatility_skew(self, market_id: str, price: float,
                                    volatility: float, option_chain: Dict) -> float:
        """
        计算波动率微笑/偏斜

        正值表示市场担忧下行风险（看跌偏斜）
        负值表示市场看好上行潜力（看涨偏斜）
        """
        if not option_chain:
            # 没有期权链数据，使用价格偏离0.5的程度作为替代
            return (price - 0.5) * 2

        # 计算不同行权价的隐含波动率差异
        iv_values = []
        for strike, data in option_chain.items():
            iv = data.get("implied_volatility", volatility)
            iv_values.append((float(strike), iv))

        if len(iv_values) < 2:
            return 0.0

        # 排序并按偏离程度加权
        iv_values.sort(key=lambda x: abs(x[0] - price))

        # 计算偏斜：价外看跌 vs 价外看涨
        otm_put_iv = next((iv for strike, iv in iv_values if strike < price), volatility)
        otm_call_iv = next((iv for strike, iv in iv_values if strike > price), volatility)

        if otm_put_iv + otm_call_iv > 0:
            skew = (otm_put_iv - otm_call_iv) / ((otm_put_iv + otm_call_iv) / 2)
        else:
            skew = 0.0

        return skew

    def _calculate_time_value_ratio(self, price: float, time_to_exp: float,
                                     intrinsic_value: float) -> float:
        """
        计算时间价值占总价值的比例

        对于二元期权，时间价值在临近到期时趋近于0
        """
        if price <= 0:
            return 0.0

        time_value = max(0, price - intrinsic_value)
        ratio = time_value / price if price > 0 else 0.0

        # 时间衰减调整
        decay_factor = min(1.0, time_to_exp / 30)  # 假设30天为基准
        ratio *= decay_factor

        return ratio


class OrderbookPressureSignalGenerator(SignalGenerator):
    """
    订单簿压力信号生成器

    分析买卖盘不平衡，检测大宗订单意图和滑点分析
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.whale_threshold: float = 10000.0  # 鲸鱼交易阈值(USD)
        self.imbalance_history: List[Dict[str, Any]] = []

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成订单簿压力信号

        Args:
            market_data: 包含以下字段:
                - market_id: 市场ID
                - orderbook: 订单簿数据
                    - bids: 买单列表 [(price, size), ...]
                    - asks: 卖单列表 [(price, size), ...]
                - trades: 近期交易列表
                - depth_levels: 分析的深度层级数

        Returns:
            Signal: 订单簿压力信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")
            orderbook = market_data.get("orderbook", {})
            trades = market_data.get("trades", [])
            depth_levels = market_data.get("depth_levels", 10)

            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            # 计算买卖盘深度
            bid_depth = sum(price * size for price, size in bids[:depth_levels])
            ask_depth = sum(price * size for price, size in asks[:depth_levels])
            total_depth = bid_depth + ask_depth

            # 计算不平衡度 (-1 到 1，正值表示买盘更强)
            imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0.0

            # 检测大宗订单(鲸鱼)
            whale_buys = sum(size * price for price, size in bids if price * size >= self.whale_threshold)
            whale_sells = sum(size * price for price, size in asks if price * size >= self.whale_threshold)
            whale_net = whale_buys - whale_sells

            # 计算滑点估计
            spread = self._calculate_spread(bids, asks)
            slippage_estimate = self._estimate_slippage(bids, asks, market_data.get("trade_size", 1000))

            # 基于买卖压力和鲸鱼活动确定信号方向
            if imbalance > 0.3 and whale_net > 0:
                # 买盘压力大 + 鲸鱼买入
                direction = SignalDirection.BULLISH
                confidence = min(0.6 + abs(imbalance) * 0.3, 1.0)
            elif imbalance < -0.3 and whale_net < 0:
                # 卖盘压力大 + 鲸鱼卖出
                direction = SignalDirection.BEARISH
                confidence = min(0.6 + abs(imbalance) * 0.3, 1.0)
            elif abs(imbalance) > 0.5:
                # 极端不平衡
                direction = SignalDirection.BULLISH if imbalance > 0 else SignalDirection.BEARISH
                confidence = min(abs(imbalance), 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5

            # 计算压力强度
            strength = abs(imbalance) * 10 + abs(whale_net) / 10000

            # 记录历史
            self.imbalance_history.append({
                "timestamp": datetime.now(),
                "market_id": market_id,
                "imbalance": imbalance,
                "whale_net": whale_net,
                "spread": spread
            })

            if len(self.imbalance_history) > 1000:
                self.imbalance_history = self.imbalance_history[-500:]

            signal = Signal(
                type=SignalType.ORDERBOOK_PRESSURE,
                direction=direction,
                confidence=confidence,
                strength=strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "imbalance_ratio": imbalance,
                    "bid_depth": bid_depth,
                    "ask_depth": ask_depth,
                    "whale_buys": whale_buys,
                    "whale_sells": whale_sells,
                    "whale_net_flow": whale_net,
                    "spread": spread,
                    "slippage_estimate": slippage_estimate,
                    "depth_levels_analyzed": depth_levels
                }
            )

            self.logger.info(
                f"OrderbookPressure signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, imbalance={imbalance:.3f}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating orderbook pressure signal: {e}")
            raise

    def _calculate_spread(self, bids: List[tuple], asks: List[tuple]) -> float:
        """计算买卖价差"""
        if not bids or not asks:
            return 0.0
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        return best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0.0

    def _estimate_slippage(self, bids: List[tuple], asks: List[tuple],
                           trade_size_usd: float) -> float:
        """估计执行滑点"""
        if not bids or not asks:
            return 0.0

        mid_price = (bids[0][0] + asks[0][0]) / 2
        if mid_price <= 0:
            return 0.0

        # 计算买入滑点
        remaining = trade_size_usd
        avg_buy_price = 0.0
        for price, size in asks:
            available = price * size
            take = min(remaining, available)
            avg_buy_price += price * (take / trade_size_usd) if trade_size_usd > 0 else 0
            remaining -= take
            if remaining <= 0:
                break

        if remaining > 0:
            # 订单簿深度不足
            return 0.1  # 10% 最大滑点

        slippage = (avg_buy_price - mid_price) / mid_price
        return max(0, slippage)


class CapitalFlowSignalGenerator(SignalGenerator):
    """
    资金流向信号生成器

    跟踪聪明钱动向，检测异常资金流动
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.smart_money_threshold: float = 0.6  # 聪明钱胜率阈值
        self.flow_window_hours: int = 24
        self.whale_threshold: float = 10000.0
        self.flow_history: List[Dict[str, Any]] = []
        self.smart_money_list: List[str] = []  # 聪明钱地址列表

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成资金流向信号

        Args:
            market_data: 包含以下字段:
                - market_id: 市场ID
                - activity_data: 活动数据
                    - trades: 交易列表
                    - inflows: 流入金额
                    - outflows: 流出金额
                    - smart_money_flows: 聪明钱流向
                    - whale_trades: 鲸鱼交易列表

        Returns:
            Signal: 资金流向信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")
            activity_data = market_data.get("activity_data", {})

            # 计算总体资金流向
            inflows = activity_data.get("inflows", 0.0)
            outflows = activity_data.get("outflows", 0.0)
            net_flow = inflows - outflows
            total_volume = inflows + outflows

            # 聪明钱流向
            smart_money_in = activity_data.get("smart_money_in", 0.0)
            smart_money_out = activity_data.get("smart_money_out", 0.0)
            smart_money_net = smart_money_in - smart_money_out

            # 鲸鱼活动
            whale_trades = activity_data.get("whale_trades", [])
            whale_buys = sum(t["size"] * t["price"] for t in whale_trades if t["side"] == "buy")
            whale_sells = sum(t["size"] * t["price"] for t in whale_trades if t["side"] == "sell")
            whale_net = whale_buys - whale_sells

            # 计算流向比率
            if total_volume > 0:
                flow_ratio = net_flow / total_volume
                smart_money_ratio = smart_money_net / total_volume if smart_money_in + smart_money_out > 0 else 0
                whale_ratio = whale_net / total_volume if whale_buys + whale_sells > 0 else 0
            else:
                flow_ratio = smart_money_ratio = whale_ratio = 0.0

            # 综合计算资金流向分数
            combined_flow = (
                flow_ratio * 0.3 +
                smart_money_ratio * 0.5 +
                whale_ratio * 0.2
            )

            # 确定信号方向
            flow_threshold = 0.2  # 20% 阈值
            if combined_flow > flow_threshold and smart_money_net > 0:
                direction = SignalDirection.BULLISH
                confidence = min(0.6 + abs(combined_flow) * 0.3, 1.0)
            elif combined_flow < -flow_threshold and smart_money_net < 0:
                direction = SignalDirection.BEARISH
                confidence = min(0.6 + abs(combined_flow) * 0.3, 1.0)
            elif abs(combined_flow) > 0.5:
                direction = SignalDirection.BULLISH if combined_flow > 0 else SignalDirection.BEARISH
                confidence = min(abs(combined_flow), 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5

            # 计算信号强度
            strength = abs(combined_flow) * 10 + abs(smart_money_net) / 10000

            # 记录历史
            self.flow_history.append({
                "timestamp": datetime.now(),
                "market_id": market_id,
                "net_flow": net_flow,
                "smart_money_net": smart_money_net,
                "whale_net": whale_net,
                "combined_flow": combined_flow
            })

            if len(self.flow_history) > 1000:
                self.flow_history = self.flow_history[-500:]

            signal = Signal(
                type=SignalType.CAPITAL_FLOW,
                direction=direction,
                confidence=confidence,
                strength=strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "inflows": inflows,
                    "outflows": outflows,
                    "net_flow": net_flow,
                    "flow_ratio": flow_ratio,
                    "smart_money_in": smart_money_in,
                    "smart_money_out": smart_money_out,
                    "smart_money_net": smart_money_net,
                    "smart_money_ratio": smart_money_ratio,
                    "whale_buys": whale_buys,
                    "whale_sells": whale_sells,
                    "whale_net": whale_net,
                    "whale_ratio": whale_ratio,
                    "whale_count": len(whale_trades),
                    "combined_flow_score": combined_flow
                }
            )

            self.logger.info(
                f"CapitalFlow signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, combined_flow={combined_flow:.3f}, "
                f"smart_money=${smart_money_net:,.0f}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating capital flow signal: {e}")
            raise


class InformationEdgeSignalGenerator(SignalGenerator):
    """
    信息优势信号生成器

    检测信息不对称，包括价格-成交量背离、抢先交易模式
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.divergence_threshold: float = 0.15  # 背离阈值
        self.anomaly_history: List[Dict[str, Any]] = []

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成信息优势信号

        Args:
            market_data: 包含以下字段:
                - market_id: 市场ID
                - price_changes: 价格变化列表
                - volume_changes: 成交量变化列表
                - news_sentiment: 新闻情绪分数 (-1 到 1)
                - unusual_activity: 异常活动标志
                - front_running_indicators: 抢先交易指标

        Returns:
            Signal: 信息优势信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")

            # 获取价格和成交量变化
            price_changes = market_data.get("price_changes", [])
            volume_changes = market_data.get("volume_changes", [])

            # 检测价格和成交量背离
            price_divergence = self._detect_price_volume_divergence(
                price_changes, volume_changes
            )

            # 检测抢先交易模式
            front_running_score = self._detect_front_running(
                market_data.get("front_running_indicators", {})
            )

            # 新闻情绪影响
            news_sentiment = market_data.get("news_sentiment", 0.0)
            news_impact = abs(news_sentiment) * 0.3 if abs(news_sentiment) > 0.5 else 0.0

            # 异常活动检测
            unusual_activity = market_data.get("unusual_activity", False)
            anomaly_boost = 0.2 if unusual_activity else 0.0

            # 综合信息优势分数
            info_score = price_divergence + front_running_score + news_impact + anomaly_boost

            # 限制在 -1 到 1 范围内
            info_score = max(-1.0, min(1.0, info_score))

            # 确定信号方向
            if info_score > 0.3:
                direction = SignalDirection.BULLISH
                confidence = min(0.6 + info_score * 0.3, 1.0)
            elif info_score < -0.3:
                direction = SignalDirection.BEARISH
                confidence = min(0.6 + abs(info_score) * 0.3, 1.0)
            elif abs(info_score) > 0.1:
                direction = SignalDirection.BULLISH if info_score > 0 else SignalDirection.BEARISH
                confidence = abs(info_score) + 0.4
            else:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5

            # 计算信号强度
            strength = abs(info_score) * 10

            # 记录历史
            self.anomaly_history.append({
                "timestamp": datetime.now(),
                "market_id": market_id,
                "info_score": info_score,
                "price_divergence": price_divergence,
                "front_running": front_running_score,
                "news_sentiment": news_sentiment
            })

            if len(self.anomaly_history) > 1000:
                self.anomaly_history = self.anomaly_history[-500:]

            signal = Signal(
                type=SignalType.INFORMATION_EDGE,
                direction=direction,
                confidence=confidence,
                strength=strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "info_score": info_score,
                    "price_volume_divergence": price_divergence,
                    "front_running_score": front_running_score,
                    "news_sentiment": news_sentiment,
                    "news_impact": news_impact,
                    "unusual_activity": unusual_activity,
                    "anomaly_boost": anomaly_boost
                }
            )

            self.logger.info(
                f"InformationEdge signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, info_score={info_score:.3f}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating information edge signal: {e}")
            raise

    def _detect_price_volume_divergence(self, price_changes: List[float],
                                         volume_changes: List[float]) -> float:
        """
        检测价格-成交量背离

        当价格上涨但成交量下降，或价格下跌但成交量上升时，
        可能存在背离信号
        """
        if len(price_changes) < 3 or len(volume_changes) < 3:
            return 0.0

        # 计算近期变化趋势
        price_trend = sum(price_changes[-3:]) / 3
        volume_trend = sum(volume_changes[-3:]) / 3

        # 背离检测：价格趋势与成交量趋势相反
        if price_trend > 0 and volume_trend < 0:
            # 价格上涨但成交量下降 - 可能缺乏支撑
            return -0.3
        elif price_trend < 0 and volume_trend > 0:
            # 价格下跌但成交量增加 - 可能底部形成
            return 0.3
        elif price_trend > 0 and volume_trend > 0:
            # 量价齐升 - 看涨确认
            return 0.2
        elif price_trend < 0 and volume_trend < 0:
            # 量价齐跌 - 看跌确认
            return -0.2

        return 0.0

    def _detect_front_running(self, indicators: Dict[str, Any]) -> float:
        """
        检测抢先交易模式

        识别可能的内幕交易或抢先交易行为
        """
        if not indicators:
            return 0.0

        score = 0.0

        # 大单提前入场
        if indicators.get("large_order_before_news", False):
            score += 0.4

        # 价格异常波动
        if indicators.get("price_spike", False):
            score += 0.3

        # 成交量异常放大
        if indicators.get("volume_surge", False):
            score += 0.2

        # 订单簿突然变化
        if indicators.get("orderbook_shift", False):
            score += 0.1

        # 根据方向调整符号
        direction = indicators.get("direction", "neutral")
        if direction == "sell":
            score = -score

        return max(-1.0, min(1.0, score))


class CompoundSignalGenerator(SignalGenerator):
    """
    复合信号生成器

    整合多个信号生成器的输出，生成综合信号
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        super().__init__(proxy_url)
        self.generators: List[SignalGenerator] = []
        self.weights: Dict[SignalType, float] = {
            SignalType.ODDS_BIAS: 0.25,
            SignalType.TIME_DECAY: 0.15,
            SignalType.ORDERBOOK_PRESSURE: 0.25,
            SignalType.CAPITAL_FLOW: 0.25,
            SignalType.INFORMATION_EDGE: 0.10
        }

    def add_generator(self, generator: SignalGenerator) -> None:
        """添加信号生成器"""
        self.generators.append(generator)

    def set_weight(self, signal_type: SignalType, weight: float) -> None:
        """设置信号类型权重"""
        self.weights[signal_type] = max(0.0, min(1.0, weight))

    async def generate(self, market_data: Dict[str, Any]) -> Signal:
        """
        生成复合信号

        Args:
            market_data: 包含各个生成器需要的所有数据

        Returns:
            Signal: 复合信号
        """
        try:
            market_id = market_data.get("market_id", "unknown")

            # 收集所有子生成器的信号
            signals: List[Signal] = []
            for generator in self.generators:
                try:
                    signal = await generator.generate(market_data)
                    if signal and signal.direction != SignalDirection.NEUTRAL:
                        signals.append(signal)
                except Exception as e:
                    self.logger.warning(f"Generator {generator.__class__.__name__} failed: {e}")

            if not signals:
                return Signal(
                    type=SignalType.COMPOUND,
                    direction=SignalDirection.NEUTRAL,
                    confidence=0.5,
                    strength=0.0,
                    timestamp=datetime.now(),
                    market_id=market_id,
                    metadata={"message": "No component signals generated"}
                )

            # 加权投票
            bullish_weight = 0.0
            bearish_weight = 0.0
            total_confidence = 0.0
            weighted_strength = 0.0

            for signal in signals:
                weight = self.weights.get(signal.type, 0.2)
                if signal.direction == SignalDirection.BULLISH:
                    bullish_weight += weight * signal.confidence
                elif signal.direction == SignalDirection.BEARISH:
                    bearish_weight += weight * signal.confidence

                total_confidence += signal.confidence * weight
                weighted_strength += signal.strength * weight

            # 确定最终方向
            net_weight = bullish_weight - bearish_weight
            if abs(net_weight) < 0.1:
                direction = SignalDirection.NEUTRAL
                confidence = 0.5
            elif net_weight > 0:
                direction = SignalDirection.BULLISH
                confidence = min(bullish_weight / (bullish_weight + bearish_weight + 0.1), 1.0)
            else:
                direction = SignalDirection.BEARISH
                confidence = min(bearish_weight / (bullish_weight + bearish_weight + 0.1), 1.0)

            strength = abs(weighted_strength)

            # 收集信号详情
            component_signals = [
                {
                    "type": s.type.value,
                    "direction": s.direction.value,
                    "confidence": s.confidence,
                    "strength": s.strength
                }
                for s in signals
            ]

            signal = Signal(
                type=SignalType.COMPOUND,
                direction=direction,
                confidence=confidence,
                strength=strength,
                timestamp=datetime.now(),
                market_id=market_id,
                metadata={
                    "bullish_weight": bullish_weight,
                    "bearish_weight": bearish_weight,
                    "net_weight": net_weight,
                    "total_confidence": total_confidence,
                    "component_count": len(signals),
                    "component_signals": component_signals
                }
            )

            self.logger.info(
                f"Compound signal generated: {direction.value}, "
                f"confidence={confidence:.3f}, net_weight={net_weight:.3f}, "
                f"components={len(signals)}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating compound signal: {e}")
            raise


# 公开接口
__all__ = [
    'Signal',
    'SignalType',
    'SignalDirection',
    'SignalGenerator',
    'OddsBiasSignalGenerator',
    'TimeDecaySignalGenerator',
    'OrderbookPressureSignalGenerator',
    'CapitalFlowSignalGenerator',
    'InformationEdgeSignalGenerator',
    'CompoundSignalGenerator',
    'LayeredSignalPipeline',
]


# =============================================================================
# LAYERED SIGNAL PIPELINE - 分层信号管道 (串行过滤)
# 流程: 数据 → 指标计算 → 市场结构分析 → 技术结论 → LLM推理
# =============================================================================

class LayeredSignalPipeline:
    """
    分层信号管道 - 串行过滤系统

    Layer 1: 风险检查 (熔断机制)
    Layer 2: 赔率偏向过滤 (至少5%优势)
    Layer 3: 时间价值 + 订单簿确认
    Layer 4: 资金流验证
    Layer 5: LLM最终决策
    """

    def __init__(
        self,
        llm_client=None,  # LLM客户端，用于第5层
        config: Dict[str, Any] = None
    ):
        self.logger = logging.getLogger(__name__)
        self.llm_client = llm_client

        # 配置
        self.config = config or {}
        self.min_odds_edge = self.config.get('min_odds_edge', 0.05)  # 最小赔率优势 5%
        self.min_composite_confidence = self.config.get('min_composite_confidence', 0.65)

        # 风险配置 (预测市场高频交易，需要放宽)
        self.daily_loss_limit = self.config.get('daily_loss_limit', 0.10)  # 默认10%熔断
        self.max_consecutive_losses = self.config.get('max_consecutive_losses', 10)  # 默认10连亏熔断
        self.max_daily_trades = self.config.get('max_daily_trades', 50)  # 每日最大交易次数

        # 信号生成器
        self.odds_generator = OddsBiasSignalGenerator()
        self.time_generator = TimeDecaySignalGenerator()
        self.orderbook_generator = OrderbookPressureSignalGenerator()
        self.capital_flow_generator = CapitalFlowSignalGenerator()
        self.information_generator = InformationEdgeSignalGenerator()

        # 风险状态
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.daily_trade_count = 0
        self.last_trade_time = None

        # 初始化子生成器
        self.compound_generator = CompoundSignalGenerator()
        self.compound_generator.add_generator(self.odds_generator)
        self.compound_generator.add_generator(self.time_generator)
        self.compound_generator.add_generator(self.orderbook_generator)
        self.compound_generator.add_generator(self.capital_flow_generator)
        self.compound_generator.add_generator(self.information_generator)

    async def generate_signal(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        """
        串行分层信号生成

        Returns:
            Signal 或 None (如果任何一层被过滤)
        """
        market_id = market_data.get('market_id', 'unknown')

        # ===== Layer 1: 风险检查 =====
        if not self._check_risk_limits():
            self.logger.info(f"[Layer1] Risk frozen for {market_id} - daily limit reached")
            return None

        # ===== Layer 2: 赔率偏向过滤 (第一关) =====
        odds_signal = await self.odds_generator.generate(market_data)
        if not odds_signal or odds_signal.direction == SignalDirection.NEUTRAL:
            self.logger.debug(f"[Layer2] {market_id} - No odds bias, filtered")
            return None

        # 检查赔率优势是否足够
        edge = abs(odds_signal.strength)
        if edge < self.min_odds_edge:
            self.logger.debug(f"[Layer2] {market_id} - Odds edge {edge:.1%} < {self.min_odds_edge:.1%}, filtered")
            return None

        self.logger.info(f"[Layer2] {market_id} - Odds bias passed, edge={edge:.1%}, direction={odds_signal.direction.value}")

        # ===== Layer 3: 时间价值 + 订单簿确认 =====
        time_signal = await self.time_generator.generate(market_data)
        orderbook_signal = await self.orderbook_generator.generate(market_data)

        # 订单簿方向必须与赔率方向一致
        if orderbook_signal and orderbook_signal.direction != SignalDirection.NEUTRAL:
            if orderbook_signal.direction != odds_signal.direction:
                self.logger.debug(f"[Layer3] {market_id} - Orderbook direction mismatch, filtered")
                return None

        # 时间价值检查 (如果事件临近时间太短，忽略时间衰减信号)
        time_left_hours = market_data.get('event_hours_until', 999)
        if time_left_hours > 1:  # 超过1小时
            if time_signal and time_signal.direction != SignalDirection.NEUTRAL:
                if time_signal.direction != odds_signal.direction:
                    self.logger.debug(f"[Layer3] {market_id} - Time decay direction mismatch")
                    return None

        self.logger.info(f"[Layer3] {market_id} - Structure checks passed")

        # ===== Layer 4: 资金流验证 =====
        flow_signal = await self.capital_flow_generator.generate(market_data)
        if flow_signal and flow_signal.direction != SignalDirection.NEUTRAL:
            # 资金流方向最好与主要方向一致，或者保持中性
            if flow_signal.direction != odds_signal.direction and flow_signal.direction != SignalDirection.NEUTRAL:
                self.logger.debug(f"[Layer4] {market_id} - Capital flow against main direction")

        self.logger.info(f"[Layer4] {market_id} - Capital flow check passed")

        # ===== Layer 5: LLM最终决策 =====
        if self.llm_client:
            decision = await self._llm_decision(market_data, odds_signal, time_signal, orderbook_signal, flow_signal)
            if not decision:
                self.logger.info(f"[Layer5] {market_id} - LLM rejected the signal")
                return None

        # ===== 生成最终信号 =====
        final_signal = await self.compound_generator.generate(market_data)

        if final_signal and final_signal.confidence >= self.min_composite_confidence:
            self.logger.info(f"[Layer5] {market_id} - Signal PASSED, confidence={final_signal.confidence:.1%}")
            return final_signal
        else:
            self.logger.info(f"[Layer5] {market_id} - Confidence too low: {final_signal.confidence if final_signal else 0:.1%}")
            return None

    def _check_risk_limits(self) -> bool:
        """
        Layer 1: 风险检查 (预测市场高频交易场景)

        - 日内亏损超过10%熔断
        - 连续亏损10次后熔断
        - 每日最大交易次数限制
        """
        # 日内亏损检查
        if self.daily_pnl <= -self.daily_loss_limit:
            self.logger.warning(f"Daily loss limit reached: {self.daily_pnl:.1%}")
            return False

        # 连续亏损检查 (放宽到10次)
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.logger.warning(f"Consecutive losses limit reached: {self.consecutive_losses}")
            return False

        # 每日交易次数限制
        if self.daily_trade_count >= self.max_daily_trades:
            self.logger.warning(f"Daily trade limit reached: {self.daily_trade_count}")
            return False

        return True

    async def _llm_decision(
        self,
        market_data: Dict,
        odds_signal: Signal,
        time_signal: Signal,
        orderbook_signal: Signal,
        flow_signal: Signal
    ) -> bool:
        """
        Layer 5: LLM最终决策

        将技术分析结论翻译成自然语言，让LLM做最终推理
        """
        if not self.llm_client:
            return True

        # 构建分析摘要 (不是原始数据!)
        analysis_summary = self._build_analysis_summary(
            market_data, odds_signal, time_signal, orderbook_signal, flow_signal
        )

        # 调用LLM
        prompt = f"""你是一个专业的Polymarket预测市场交易员。

市场分析摘要:
{analysis_summary}

根据以上分析，决定是否执行交易。回复格式:
- 如果决定买入: BUY <原因简短说明>
- 如果决定卖出: SELL <原因简短说明>
- 如果决定等待: WAIT <原因简短说明>"""

        try:
            response = await self.llm_client.chat(prompt)
            if response and 'BUY' in response.upper():
                return True
            elif response and 'SELL' in response.upper():
                # 这里返回True，因为SELL方向也会被主逻辑处理
                return True
            else:
                return False
        except Exception as e:
            self.logger.error(f"LLM decision failed: {e}")
            return False  # LLM失败时保守处理

    def _build_analysis_summary(
        self,
        market_data: Dict,
        odds_signal: Signal,
        time_signal: Signal,
        orderbook_signal: Signal,
        flow_signal: Signal
    ) -> str:
        """构建分析摘要 - 将数值翻译成结论语言"""

        market_id = market_data.get('market_id', 'unknown')
        yes_price = market_data.get('yes_price', 0.5)
        no_price = market_data.get('no_price', 0.5)
        volume = market_data.get('volume', 0)
        event_hours = market_data.get('event_hours_until', 0)

        # 趋势方向
        trend = "看涨" if odds_signal.direction == SignalDirection.BULLISH else "看跌" if odds_signal.direction == SignalDirection.BEARISH else "中性"

        # 强度描述
        edge_pct = abs(odds_signal.strength) * 100
        if edge_pct >= 10:
            edge_desc = "非常强"
        elif edge_pct >= 5:
            edge_desc = "较强"
        else:
            edge_desc = "一般"

        # 时间价值
        if event_hours > 24:
            time_desc = f"事件还有{event_hours:.0f}小时，时间价值高"
        elif event_hours > 1:
            time_desc = f"事件还有{event_hours:.1f}小时，时间价值中等"
        else:
            time_desc = "即将到期，时间价值低"

        # 订单簿
        if orderbook_signal and orderbook_signal.strength > 0:
            ob_desc = f"订单簿压力{('买方' if orderbook_signal.direction == SignalDirection.BULLISH else '卖方')}占优"
        else:
            ob_desc = "订单簿平衡"

        # 资金流
        if flow_signal and flow_signal.strength > 0.5:
            flow_desc = "有大额资金流入"
        elif flow_signal and flow_signal.strength < -0.5:
            flow_desc = "有大额资金流出"
        else:
            flow_desc = "资金流平稳"

        # 组装摘要
        summary = f"""
市场: {market_id}
当前价格: Yes={yes_price:.1%}, No={no_price:.1%}
趋势: {trend}, 概率优势: {edge_desc}({edge_pct:.1f}%)
时间: {time_desc}
订单簿: {ob_desc}
资金流: {flow_desc}
"""
        return summary

    def update_pnl(self, pnl: float):
        """更新每日盈亏"""
        self.daily_pnl += pnl
        self.daily_trade_count += 1
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        self.last_trade_time = datetime.now()

    def reset_daily(self):
        """重置每日状态 (UTC 0点调用)"""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.daily_trade_count = 0
