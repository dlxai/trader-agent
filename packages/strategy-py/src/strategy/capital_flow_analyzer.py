"""
资金流分析辅助决策系统 (Capital Flow Analyzer)

实现资金流分析辅助止盈止损功能，包括：
1. 资金流数据收集器 (CapitalFlowCollector) - 净资金流统计、唯一交易者数量、价格变动关联
2. 资金流信号计算器 (FlowSignalCalculator) - 资金加速信号、极端流检测、连续流统计
3. 辅助决策引擎 (FlowAssistedDecision) - 权重分配、信号融合、极端情况处理
4. 统计和报告模块 (FlowAnalytics) - 检测准确率、资金流失效分析、历史回测

技术栈：
- Pandas/NumPy 进行高效数值计算
- 滑动窗口算法优化性能
- 完整类型注解和文档
- 可配置化参数设计
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from collections import deque

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from config.settings import settings

logger = logging.getLogger(__name__)


# =============================================================================
# 枚举类型定义
# =============================================================================

class FlowDirection(Enum):
    """资金流向方向"""
    POSITIVE = "positive"      # 正向流入
    NEGATIVE = "negative"      # 负向流出
    NEUTRAL = "neutral"        # 中性平衡


class SignalStrength(Enum):
    """信号强度等级"""
    EXTREME = 4        # 极端信号 (> 3σ)
    STRONG = 3         # 强信号 (2-3σ)
    MODERATE = 2       # 中等信号 (1-2σ)
    WEAK = 1           # 弱信号 (< 1σ)
    NONE = 0           # 无信号


class DecisionAction(Enum):
    """决策行动"""
    EXIT_IMMEDIATELY = "exit_immediately"      # 立即退出
    ACCELERATE_EXIT = "accelerate_exit"        # 加速退出
    HOLD_WITH_CAUTION = "hold_with_caution"    # 谨慎持有
    DELAY_EXIT = "delay_exit"                  # 推迟退出
    NO_ACTION = "no_action"                    # 无操作


# =============================================================================
# 数据结构定义
# =============================================================================

@dataclass
class TradeRecord:
    """单笔交易记录"""
    timestamp: datetime
    price: float
    size: float
    side: str  # "buy" or "sell"
    trader_id: Optional[str] = None


@dataclass
class FlowMetrics:
    """资金流指标（单时间窗口）"""
    timestamp: datetime
    window_seconds: int

    # 净资金流
    net_flow: float
    inflow: float
    outflow: float

    # 唯一交易者统计
    unique_buyers: int
    unique_sellers: int
    total_unique_traders: int

    # 价格变动关联
    price_change: float
    price_change_pct: float
    volume: float

    # 衍生指标
    flow_velocity: float  # 资金流速
    buy_sell_ratio: float  # 买卖比


@dataclass
class FlowSignal:
    """资金流信号"""
    timestamp: datetime
    signal_type: str
    direction: FlowDirection
    strength: SignalStrength
    confidence: float  # 0-1

    # 信号详情
    metrics: Dict[str, float]
    description: str

    # 建议行动
    suggested_action: DecisionAction
    priority: int  # 优先级 (1-10)


@dataclass
class DecisionResult:
    """决策结果"""
    timestamp: datetime
    position_id: str

    # 决策输入
    price_signal: Optional[Dict[str, Any]]
    flow_signal: Optional[FlowSignal]

    # 决策输出
    action: DecisionAction
    exit_ratio: float  # 建议退出比例
    confidence: float  # 决策置信度

    # 决策理由
    reasoning: List[str]
    risk_factors: List[str]

    # 权重配置快照
    weights_snapshot: Dict[str, float]


@dataclass
class PerformanceMetrics:
    """性能统计指标"""
    total_predictions: int = 0
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    # 时间序列
    prediction_history: List[Dict] = field(default_factory=list)
    accuracy_trend: List[float] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.0
        return (self.true_positives + self.true_negatives) / self.total_predictions

    @property
    def precision(self) -> float:
        if (self.true_positives + self.false_positives) == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        if (self.true_positives + self.false_negatives) == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        if (p + r) == 0:
            return 0.0
        return 2 * p * r / (p + r)


# =============================================================================
# 1. 资金流数据收集器 (CapitalFlowCollector)
# =============================================================================

class CapitalFlowCollector:
    """
    资金流数据收集器

    负责实时收集和统计资金流数据，包括：
    - 净资金流统计（1分钟、5分钟、15分钟窗口）
    - 唯一交易者数量统计
    - 价格变动关联分析
    - 成交量分布分析

    使用滑动窗口算法优化性能，支持 Pandas/NumPy 高效计算。
    """

    # 默认窗口配置（秒）
    DEFAULT_WINDOWS = [60, 300, 900]  # 1分钟、5分钟、15分钟

    def __init__(
        self,
        windows: Optional[List[int]] = None,
        max_history: int = 10000,
        config: Optional[Dict] = None
    ):
        """
        初始化资金流收集器

        Args:
            windows: 时间窗口列表（秒），默认 [60, 300, 900]
            max_history: 最大历史记录数
            config: 自定义配置
        """
        self.windows = windows or self.DEFAULT_WINDOWS
        self.max_history = max_history
        self.config = config or {}

        # 原始交易记录队列 (时间戳, 价格, 数量, 方向, 交易者ID)
        self._trades: deque = deque(maxlen=max_history)

        # 缓存的 DataFrame (定期重建)
        self._df_cache: Optional[pd.DataFrame] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 1.0  # 缓存1秒

        # 预计算的窗口指标缓存
        self._metrics_cache: Dict[int, FlowMetrics] = {}

        # 统计信息
        self._stats = {
            "total_trades": 0,
            "total_volume": 0.0,
            "start_time": datetime.now(),
        }

        logger.info(
            f"CapitalFlowCollector initialized with windows={self.windows}, "
            f"max_history={max_history}"
        )

    def add_trade(
        self,
        timestamp: Union[datetime, float],
        price: float,
        size: float,
        side: str,
        trader_id: Optional[str] = None
    ) -> None:
        """
        添加单笔交易记录

        Args:
            timestamp: 交易时间戳 (datetime 或 Unix 时间戳)
            price: 成交价格
            size: 成交量
            side: 方向 ("buy" 或 "sell")
            trader_id: 交易者标识 (用于统计唯一交易者)
        """
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp)

        trade = TradeRecord(
            timestamp=timestamp,
            price=price,
            size=size,
            side=side.lower(),
            trader_id=trader_id
        )

        self._trades.append(trade)

        # 更新统计
        self._stats["total_trades"] += 1
        self._stats["total_volume"] += size

        # 清除缓存 (下次查询时重建)
        self._cache_timestamp = 0

    def add_trades_batch(self, trades: List[Dict]) -> None:
        """
        批量添加交易记录

        Args:
            trades: 交易记录列表，每条记录包含 timestamp, price, size, side, trader_id
        """
        for trade_data in trades:
            self.add_trade(
                timestamp=trade_data.get("timestamp", datetime.now()),
                price=trade_data["price"],
                size=trade_data["size"],
                side=trade_data["side"],
                trader_id=trade_data.get("trader_id")
            )

    def get_flow_metrics(self, window_seconds: Optional[int] = None) -> FlowMetrics:
        """
        获取指定窗口的资金流指标

        Args:
            window_seconds: 时间窗口（秒），默认使用第一个配置窗口

        Returns:
            FlowMetrics: 资金流指标
        """
        window = window_seconds or self.windows[0]

        # 检查缓存
        cache_key = window
        current_time = time.time()
        if cache_key in self._metrics_cache:
            cached = self._metrics_cache[cache_key]
            # 缓存有效1秒
            if (current_time - cached.timestamp.timestamp()) < 1.0:
                return cached

        # 计算指标
        df = self._get_dataframe()
        if df.empty:
            return self._empty_metrics(window)

        # 筛选窗口内的数据
        cutoff_time = datetime.now() - timedelta(seconds=window)
        window_df = df[df["timestamp"] >= cutoff_time]

        if window_df.empty:
            return self._empty_metrics(window)

        # 净资金流计算
        buys = window_df[window_df["side"] == "buy"]
        sells = window_df[window_df["side"] == "sell"]

        inflow = (buys["price"] * buys["size"]).sum() if not buys.empty else 0.0
        outflow = (sells["price"] * sells["size"]).sum() if not sells.empty else 0.0
        net_flow = inflow - outflow

        # 唯一交易者统计
        unique_buyers = buys["trader_id"].nunique() if not buys.empty and "trader_id" in buys.columns else 0
        unique_sellers = sells["trader_id"].nunique() if not sells.empty and "trader_id" in sells.columns else 0
        total_unique = window_df["trader_id"].nunique() if "trader_id" in window_df.columns else 0

        # 价格变动关联
        if len(window_df) >= 2:
            start_price = window_df.iloc[0]["price"]
            end_price = window_df.iloc[-1]["price"]
            price_change = end_price - start_price
            price_change_pct = (price_change / start_price) * 100 if start_price > 0 else 0.0
        else:
            price_change = 0.0
            price_change_pct = 0.0

        # 成交量
        volume = window_df["size"].sum()

        # 衍生指标
        flow_velocity = net_flow / window if window > 0 else 0.0
        buy_sell_ratio = (inflow / outflow) if outflow > 0 else (999.0 if inflow > 0 else 1.0)

        metrics = FlowMetrics(
            timestamp=datetime.now(),
            window_seconds=window,
            net_flow=net_flow,
            inflow=inflow,
            outflow=outflow,
            unique_buyers=int(unique_buyers),
            unique_sellers=int(unique_sellers),
            total_unique_traders=int(total_unique),
            price_change=price_change,
            price_change_pct=price_change_pct,
            volume=volume,
            flow_velocity=flow_velocity,
            buy_sell_ratio=buy_sell_ratio,
        )

        # 更新缓存
        self._metrics_cache[cache_key] = metrics

        return metrics

    def get_multi_window_metrics(self) -> Dict[int, FlowMetrics]:
        """
        获取多个窗口的资金流指标

        Returns:
            Dict[int, FlowMetrics]: 窗口大小 -> 指标 的映射
        """
        return {window: self.get_flow_metrics(window) for window in self.windows}

    def get_flow_distribution(self, window_seconds: int = 300, bins: int = 10) -> Dict:
        """
        获取资金流分布分析

        Args:
            window_seconds: 分析窗口（秒）
            bins: 分箱数量

        Returns:
            Dict: 分布统计信息
        """
        df = self._get_dataframe()
        if df.empty:
            return {"error": "No data available"}

        cutoff_time = datetime.now() - timedelta(seconds=window_seconds)
        window_df = df[df["timestamp"] >= cutoff_time]

        if window_df.empty:
            return {"error": "No data in window"}

        # 按分钟聚合
        window_df = window_df.copy()
        window_df["minute"] = window_df["timestamp"].dt.floor("min")

        minute_flows = []
        for minute, group in window_df.groupby("minute"):
            buys = group[group["side"] == "buy"]
            sells = group[group["side"] == "sell"]
            inflow = (buys["price"] * buys["size"]).sum()
            outflow = (sells["price"] * sells["size"]).sum()
            minute_flows.append(inflow - outflow)

        if not minute_flows:
            return {"error": "No flow data"}

        flows = np.array(minute_flows)

        return {
            "window_seconds": window_seconds,
            "data_points": len(flows),
            "mean": float(np.mean(flows)),
            "std": float(np.std(flows)),
            "min": float(np.min(flows)),
            "max": float(np.max(flows)),
            "median": float(np.median(flows)),
            "percentiles": {
                "5": float(np.percentile(flows, 5)),
                "25": float(np.percentile(flows, 25)),
                "75": float(np.percentile(flows, 75)),
                "95": float(np.percentile(flows, 95)),
            },
            "histogram": {
                "bins": bins,
                "counts": np.histogram(flows, bins=bins)[0].tolist(),
            },
        }

    def _get_dataframe(self) -> pd.DataFrame:
        """获取交易数据的 DataFrame（带缓存）"""
        current_time = time.time()

        # 检查缓存有效性
        if (self._df_cache is not None and
            (current_time - self._cache_timestamp) < self._cache_ttl):
            return self._df_cache

        if not self._trades:
            return pd.DataFrame()

        # 构建 DataFrame
        data = {
            "timestamp": [t.timestamp for t in self._trades],
            "price": [t.price for t in self._trades],
            "size": [t.size for t in self._trades],
            "side": [t.side for t in self._trades],
            "trader_id": [t.trader_id for t in self._trades],
        }

        df = pd.DataFrame(data)
        self._df_cache = df
        self._cache_timestamp = current_time

        return df

    def _empty_metrics(self, window_seconds: int) -> FlowMetrics:
        """创建空指标对象"""
        return FlowMetrics(
            timestamp=datetime.now(),
            window_seconds=window_seconds,
            net_flow=0.0,
            inflow=0.0,
            outflow=0.0,
            unique_buyers=0,
            unique_sellers=0,
            total_unique_traders=0,
            price_change=0.0,
            price_change_pct=0.0,
            volume=0.0,
            flow_velocity=0.0,
            buy_sell_ratio=1.0,
        )

    def get_stats(self) -> Dict:
        """获取收集器统计信息"""
        return {
            "total_trades": self._stats["total_trades"],
            "total_volume": self._stats["total_volume"],
            "uptime_seconds": (datetime.now() - self._stats["start_time"]).total_seconds(),
            "windows_config": self.windows,
            "cache_stats": {
                "cache_size": len(self._trades),
                "max_history": self.max_history,
            },
        }


# =============================================================================
# 2. 资金流信号计算器 (FlowSignalCalculator)
# =============================================================================

class FlowSignalCalculator:
    """
    资金流信号计算器

    基于资金流数据计算各类交易信号：
    - 资金加速信号（连续多分钟流入/流出加速）
    - 极端流检测（超过历史均值2倍标准差）
    - 连续流统计（连续N分钟同向流入/流出）
    - 资金流向强度评分
    """

    def __init__(
        self,
        history_window: int = 300,  # 历史数据窗口（5分钟）
        acceleration_lookback: int = 3,  # 加速检测回看期数
        extreme_std_threshold: float = 2.0,  # 极端流标准差阈值
        consecutive_threshold: int = 3,  # 连续流阈值
        config: Optional[Dict] = None
    ):
        """
        初始化信号计算器

        Args:
            history_window: 历史数据窗口大小
            acceleration_lookback: 加速检测回看期数
            extreme_std_threshold: 极端流标准差倍数阈值
            consecutive_threshold: 连续流判定阈值
            config: 自定义配置
        """
        self.history_window = history_window
        self.acceleration_lookback = acceleration_lookback
        self.extreme_std_threshold = extreme_std_threshold
        self.consecutive_threshold = consecutive_threshold
        self.config = config or {}

        # 历史资金流数据队列 (时间戳, 净资金流)
        self._flow_history: deque = deque(maxlen=history_window)
        self._minute_flows: deque = deque(maxlen=100)  # 分钟级聚合

        # 统计缓存
        self._stats_cache: Dict = {}
        self._last_calc_time: float = 0

        logger.info(
            f"FlowSignalCalculator initialized: "
            f"history_window={history_window}, "
            f"extreme_threshold={extreme_std_threshold}σ"
        )

    def add_minute_flow(self, timestamp: datetime, net_flow: float) -> None:
        """
        添加分钟级资金流数据

        Args:
            timestamp: 时间戳
            net_flow: 净资金流（正为流入，负为流出）
        """
        self._minute_flows.append((timestamp, net_flow))
        self._flow_history.append((timestamp, net_flow))

    def calculate_signals(self) -> List[FlowSignal]:
        """
        计算所有类型的资金流信号

        Returns:
            List[FlowSignal]: 检测到的信号列表
        """
        signals = []

        # 检查是否有足够数据
        if len(self._minute_flows) < self.acceleration_lookback:
            return signals

        # 1. 资金加速信号
        accel_signal = self._detect_acceleration()
        if accel_signal:
            signals.append(accel_signal)

        # 2. 极端流检测
        extreme_signal = self._detect_extreme_flow()
        if extreme_signal:
            signals.append(extreme_signal)

        # 3. 连续流统计
        consecutive_signal = self._detect_consecutive_flow()
        if consecutive_signal:
            signals.append(consecutive_signal)

        # 4. 资金流向强度
        strength_signal = self._calculate_flow_strength()
        if strength_signal:
            signals.append(strength_signal)

        return signals

    def _detect_acceleration(self) -> Optional[FlowSignal]:
        """
        检测资金加速信号

        检测逻辑：
        - 连续 N 分钟同向流入/流出
        - 且流速逐分钟增加
        """
        if len(self._minute_flows) < self.acceleration_lookback:
            return None

        # 取最近 N 分钟
        recent = list(self._minute_flows)[-self.acceleration_lookback:]

        # 检查是否同向
        flows = [f[1] for f in recent]
        all_positive = all(f > 0 for f in flows)
        all_negative = all(f < 0 for f in flows)

        if not (all_positive or all_negative):
            return None

        # 检查是否加速（逐分钟绝对值增加）
        abs_flows = [abs(f) for f in flows]
        is_accelerating = all(
            abs_flows[i] < abs_flows[i+1]
            for i in range(len(abs_flows)-1)
        )

        if not is_accelerating:
            return None

        # 确定信号强度和方向
        direction = FlowDirection.POSITIVE if all_positive else FlowDirection.NEGATIVE
        avg_acceleration = (abs_flows[-1] - abs_flows[0]) / len(abs_flows)

        if avg_acceleration > 3.0:
            strength = SignalStrength.EXTREME
        elif avg_acceleration > 2.0:
            strength = SignalStrength.STRONG
        elif avg_acceleration > 1.0:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # 建议行动
        if direction == FlowDirection.NEGATIVE:
            if strength.value >= SignalStrength.STRONG.value:
                suggested_action = DecisionAction.EXIT_IMMEDIATELY
            else:
                suggested_action = DecisionAction.ACCELERATE_EXIT
        else:
            suggested_action = DecisionAction.HOLD_WITH_CAUTION

        return FlowSignal(
            timestamp=datetime.now(),
            signal_type="acceleration",
            direction=direction,
            strength=strength,
            confidence=min(0.9, 0.5 + strength.value * 0.1),
            metrics={
                "acceleration_rate": avg_acceleration,
                "consecutive_minutes": len(flows),
                "latest_flow": flows[-1],
            },
            description=f"资金{direction.value}加速: {avg_acceleration:.2f}/分钟, 连续{len(flows)}分钟",
            suggested_action=suggested_action,
            priority=strength.value + 2
        )

    def _detect_extreme_flow(self) -> Optional[FlowSignal]:
        """
        检测极端资金流

        检测逻辑：
        - 当前资金流超过历史均值 N 倍标准差
        """
        if len(self._flow_history) < 30:  # 需要足够历史数据
            return None

        flows = np.array([f[1] for f in self._flow_history])
        mean = np.mean(flows)
        std = np.std(flows)

        if std == 0:
            return None

        # 获取最新资金流
        latest_flow = self._minute_flows[-1][1] if self._minute_flows else 0
        z_score = (latest_flow - mean) / std

        # 判断是否极端
        if abs(z_score) < self.extreme_std_threshold:
            return None

        # 确定方向和强度
        direction = FlowDirection.POSITIVE if latest_flow > 0 else FlowDirection.NEGATIVE

        if abs(z_score) > 4.0:
            strength = SignalStrength.EXTREME
        elif abs(z_score) > 3.0:
            strength = SignalStrength.STRONG
        else:
            strength = SignalStrength.MODERATE

        # 建议行动
        if direction == FlowDirection.NEGATIVE:
            suggested_action = DecisionAction.EXIT_IMMEDIATELY if strength.value >= SignalStrength.STRONG.value else DecisionAction.ACCELERATE_EXIT
        else:
            suggested_action = DecisionAction.HOLD_WITH_CAUTION

        return FlowSignal(
            timestamp=datetime.now(),
            signal_type="extreme_flow",
            direction=direction,
            strength=strength,
            confidence=min(0.95, 0.6 + abs(z_score) * 0.05),
            metrics={
                "z_score": z_score,
                "mean": mean,
                "std": std,
                "latest_flow": latest_flow,
            },
            description=f"极端资金{direction.value}: Z-score={z_score:.2f} ({strength.name})",
            suggested_action=suggested_action,
            priority=strength.value + 3
        )

    def _detect_consecutive_flow(self) -> Optional[FlowSignal]:
        """
        检测连续资金流

        检测逻辑：
        - 连续 N 分钟同向资金流
        """
        if len(self._minute_flows) < self.consecutive_threshold:
            return None

        # 统计连续同向
        flows = list(self._minute_flows)
        consecutive_count = 1
        direction = FlowDirection.POSITIVE if flows[-1][1] > 0 else FlowDirection.NEGATIVE

        for i in range(len(flows) - 2, -1, -1):
            flow = flows[i][1]
            if direction == FlowDirection.POSITIVE and flow > 0:
                consecutive_count += 1
            elif direction == FlowDirection.NEGATIVE and flow < 0:
                consecutive_count += 1
            else:
                break

        if consecutive_count < self.consecutive_threshold:
            return None

        # 计算累计流量
        total_flow = sum(abs(f[1]) for f in flows[-consecutive_count:])

        # 确定强度
        if consecutive_count >= 10:
            strength = SignalStrength.EXTREME
        elif consecutive_count >= 7:
            strength = SignalStrength.STRONG
        elif consecutive_count >= 5:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # 建议行动
        if direction == FlowDirection.NEGATIVE:
            if strength.value >= SignalStrength.MODERATE.value:
                suggested_action = DecisionAction.EXIT_IMMEDIATELY
            else:
                suggested_action = DecisionAction.ACCELERATE_EXIT
        else:
            suggested_action = DecisionAction.HOLD_WITH_CAUTION

        return FlowSignal(
            timestamp=datetime.now(),
            signal_type="consecutive_flow",
            direction=direction,
            strength=strength,
            confidence=min(0.9, 0.4 + consecutive_count * 0.05),
            metrics={
                "consecutive_minutes": consecutive_count,
                "total_flow": total_flow,
                "avg_flow_per_minute": total_flow / consecutive_count,
            },
            description=f"连续{direction.value}{consecutive_count}分钟, 累计流量={total_flow:.2f}",
            suggested_action=suggested_action,
            priority=min(10, consecutive_count)
        )

    def _calculate_flow_strength(self) -> Optional[FlowSignal]:
        """
        计算资金流向强度评分

        综合多个维度计算资金强度评分 (0-100)
        """
        if len(self._minute_flows) < 3:
            return None

        # 获取最近数据
        recent = list(self._minute_flows)[-5:]  # 最近5分钟
        flows = [f[1] for f in recent]

        # 1. 量能力度 (40%)
        total_volume = sum(abs(f) for f in flows)
        volume_score = min(40, total_volume / 1000 * 40)  # 归一化到40分

        # 2. 趋势一致性 (30%)
        positive_count = sum(1 for f in flows if f > 0)
        negative_count = len(flows) - positive_count
        consistency_score = max(positive_count, negative_count) / len(flows) * 30

        # 3. 加速度 (20%)
        if len(flows) >= 3:
            diffs = [flows[i+1] - flows[i] for i in range(len(flows)-1)]
            accel = sum(diffs[1:]) - sum(diffs[:-1]) if len(diffs) >= 2 else 0
            accel_score = min(20, max(0, (accel / 100 + 10)))  # 归一化
        else:
            accel_score = 10

        # 4. 持续性 (10%)
        sustained_score = 10 if len(flows) >= 5 else (len(flows) / 5 * 10)

        # 总分
        total_score = volume_score + consistency_score + accel_score + sustained_score

        # 确定方向
        net_flow = sum(flows)
        direction = FlowDirection.POSITIVE if net_flow > 0 else FlowDirection.NEGATIVE

        # 确定强度等级
        if total_score >= 80:
            strength = SignalStrength.EXTREME
        elif total_score >= 60:
            strength = SignalStrength.STRONG
        elif total_score >= 40:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # 建议行动
        if direction == FlowDirection.NEGATIVE:
            if total_score >= 60:
                suggested_action = DecisionAction.EXIT_IMMEDIATELY
            elif total_score >= 40:
                suggested_action = DecisionAction.ACCELERATE_EXIT
            else:
                suggested_action = DecisionAction.HOLD_WITH_CAUTION
        else:
            suggested_action = DecisionAction.HOLD_WITH_CAUTION

        return FlowSignal(
            timestamp=datetime.now(),
            signal_type="flow_strength",
            direction=direction,
            strength=strength,
            confidence=total_score / 100,
            metrics={
                "total_score": total_score,
                "volume_score": volume_score,
                "consistency_score": consistency_score,
                "accel_score": accel_score,
                "sustained_score": sustained_score,
                "net_flow": net_flow,
            },
            description=f"资金强度评分: {total_score:.1f}/100 ({direction.value}, {strength.name})",
            suggested_action=suggested_action,
            priority=int(total_score / 10)
        )

    def get_stats(self) -> Dict:
        """获取计算器统计信息"""
        return {
            "history_size": len(self._flow_history),
            "minute_flows_size": len(self._minute_flows),
            "config": {
                "history_window": self.history_window,
                "acceleration_lookback": self.acceleration_lookback,
                "extreme_std_threshold": self.extreme_std_threshold,
                "consecutive_threshold": self.consecutive_threshold,
            },
        }


# =============================================================================
# 3. 辅助决策引擎 (FlowAssistedDecision)
# =============================================================================

class FlowAssistedDecision:
    """
    辅助决策引擎

    融合价格信号和资金流信号，提供智能决策：
    - 权重分配：价格基础退出权重(0.7) + 资金流加速权重(0.3)
    - 信号融合逻辑：价格信号为主，资金流为辅
    - 极端情况处理：资金流异常时提前退出或推迟退出
    - 置信度计算：结合多个信号来源的不确定性
    """

    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "price_based_exit": 0.7,       # 价格基础退出权重（主）
        "flow_acceleration": 0.3,     # 资金流加速权重（辅）
    }

    # 信号优先级映射
    PRIORITY_MAP = {
        "price_stop_loss": 10,          # 价格止损最高优先级
        "price_take_profit": 9,       # 价格止盈
        "extreme_negative_flow": 8,   # 极端负向资金流
        "consecutive_negative_flow": 7, # 连续负向资金流
        "accelerating_negative_flow": 6, # 加速负向资金流
        "flow_strength_negative": 5,   # 资金强度负向
        "flow_strength_positive": 3,   # 资金强度正向
        "accelerating_positive_flow": 2, # 加速正向资金流
        "consecutive_positive_flow": 1, # 连续正向资金流
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        confidence_threshold: float = 0.6,
        enable_extreme_override: bool = True,
        config: Optional[Dict] = None
    ):
        """
        初始化辅助决策引擎

        Args:
            weights: 自定义权重配置
            confidence_threshold: 置信度阈值
            enable_extreme_override: 是否启用极端情况覆盖
            config: 额外配置
        """
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.confidence_threshold = confidence_threshold
        self.enable_extreme_override = enable_extreme_override
        self.config = config or {}

        # 历史决策记录
        self._decision_history: deque = deque(maxlen=1000)

        # 累计统计
        self._stats = {
            "total_decisions": 0,
            "price_based_decisions": 0,
            "flow_based_decisions": 0,
            "fused_decisions": 0,
            "extreme_overrides": 0,
        }

        logger.info(
            f"FlowAssistedDecision initialized: "
            f"weights={self.weights}, confidence_threshold={confidence_threshold}"
        )

    def make_decision(
        self,
        position_id: str,
        price_signal: Optional[Dict[str, Any]],
        flow_signals: List[FlowSignal],
        context: Optional[Dict] = None
    ) -> DecisionResult:
        """
        综合价格信号和资金流信号做出决策

        Args:
            position_id: 持仓ID
            price_signal: 价格信号（如止盈止损触发）
            flow_signals: 资金流信号列表
            context: 额外上下文信息

        Returns:
            DecisionResult: 决策结果
        """
        timestamp = datetime.now()
        context = context or {}

        # 分析价格信号
        price_action = self._analyze_price_signal(price_signal)

        # 分析资金流信号
        flow_action, flow_confidence = self._analyze_flow_signals(flow_signals)

        # 融合决策
        final_action, exit_ratio, confidence, reasoning = self._fuse_decisions(
            price_action, flow_action, flow_confidence, flow_signals
        )

        # 极端情况覆盖
        if self.enable_extreme_override:
            final_action = self._apply_extreme_override(
                final_action, price_signal, flow_signals
            )

        # 计算风险因素
        risk_factors = self._assess_risk_factors(
            price_signal, flow_signals, final_action
        )

        # 更新统计
        self._update_stats(price_action, flow_action, final_action)

        result = DecisionResult(
            timestamp=timestamp,
            position_id=position_id,
            price_signal=price_signal,
            flow_signal=flow_signals[0] if flow_signals else None,
            action=final_action,
            exit_ratio=exit_ratio,
            confidence=confidence,
            reasoning=reasoning,
            risk_factors=risk_factors,
            weights_snapshot=self.weights.copy()
        )

        # 记录历史
        self._decision_history.append({
            "timestamp": timestamp,
            "position_id": position_id,
            "result": result
        })

        return result

    def _analyze_price_signal(
        self,
        price_signal: Optional[Dict[str, Any]]
    ) -> DecisionAction:
        """分析价格信号"""
        if not price_signal:
            return DecisionAction.NO_ACTION

        signal_type = price_signal.get("type", "").lower()

        if "stop_loss" in signal_type:
            return DecisionAction.EXIT_IMMEDIATELY
        elif "take_profit" in signal_type:
            return DecisionAction.ACCELERATE_EXIT
        elif "trailing_stop" in signal_type:
            return DecisionAction.EXIT_IMMEDIATELY

        return DecisionAction.NO_ACTION

    def _analyze_flow_signals(
        self,
        flow_signals: List[FlowSignal]
    ) -> Tuple[DecisionAction, float]:
        """
        分析资金流信号

        Returns:
            (建议行动, 置信度)
        """
        if not flow_signals:
            return DecisionAction.NO_ACTION, 0.0

        # 按优先级排序
        sorted_signals = sorted(
            flow_signals,
            key=lambda s: (s.strength.value, s.priority),
            reverse=True
        )

        strongest = sorted_signals[0]

        # 根据信号类型和强度确定行动
        if strongest.direction == FlowDirection.NEGATIVE:
            if strongest.strength.value >= SignalStrength.STRONG.value:
                action = DecisionAction.EXIT_IMMEDIATELY
            elif strongest.strength.value >= SignalStrength.MODERATE.value:
                action = DecisionAction.ACCELERATE_EXIT
            else:
                action = DecisionAction.HOLD_WITH_CAUTION
        else:  # POSITIVE
            if strongest.strength.value >= SignalStrength.STRONG.value:
                action = DecisionAction.DELAY_EXIT
            else:
                action = DecisionAction.NO_ACTION

        return action, strongest.confidence

    def _fuse_decisions(
        self,
        price_action: DecisionAction,
        flow_action: DecisionAction,
        flow_confidence: float,
        flow_signals: List[FlowSignal]
    ) -> Tuple[DecisionAction, float, float, List[str]]:
        """
        融合价格信号和资金流信号

        Returns:
            (最终行动, 退出比例, 置信度, 推理过程)
        """
        reasoning = []

        # 价格信号权重
        price_weight = self.weights.get("price_based_exit", 0.7)
        flow_weight = self.weights.get("flow_acceleration", 0.3)

        # 价格信号强度评估
        price_strength = self._action_to_score(price_action)

        # 资金流信号强度
        flow_strength = self._action_to_score(flow_action) * flow_confidence

        # 加权融合
        fused_score = price_strength * price_weight + flow_strength * flow_weight

        # 置信度计算
        confidence = self._calculate_fusion_confidence(
            price_action, flow_action, flow_confidence, flow_signals
        )

        # 转换为行动
        final_action = self._score_to_action(fused_score)

        # 计算退出比例
        exit_ratio = self._calculate_exit_ratio(final_action, fused_score)

        # 构建推理过程
        reasoning.append(f"价格信号: {price_action.value} (权重{price_weight:.0%})")
        reasoning.append(f"资金流信号: {flow_action.value} (权重{flow_weight:.0%}, 置信度{flow_confidence:.1%})")
        reasoning.append(f"融合得分: {fused_score:.2f} -> 决策: {final_action.value}")
        reasoning.append(f"决策置信度: {confidence:.1%}")

        return final_action, exit_ratio, confidence, reasoning

    def _action_to_score(self, action: DecisionAction) -> float:
        """将行动转换为分数 (-1 到 1)"""
        scores = {
            DecisionAction.EXIT_IMMEDIATELY: -1.0,
            DecisionAction.ACCELERATE_EXIT: -0.6,
            DecisionAction.HOLD_WITH_CAUTION: -0.2,
            DecisionAction.NO_ACTION: 0.0,
            DecisionAction.DELAY_EXIT: 0.3,
        }
        return scores.get(action, 0.0)

    def _score_to_action(self, score: float) -> DecisionAction:
        """将分数转换为行动"""
        if score <= -0.8:
            return DecisionAction.EXIT_IMMEDIATELY
        elif score <= -0.4:
            return DecisionAction.ACCELERATE_EXIT
        elif score <= -0.1:
            return DecisionAction.HOLD_WITH_CAUTION
        elif score <= 0.2:
            return DecisionAction.NO_ACTION
        else:
            return DecisionAction.DELAY_EXIT

    def _calculate_fusion_confidence(
        self,
        price_action: DecisionAction,
        flow_action: DecisionAction,
        flow_confidence: float,
        flow_signals: List[FlowSignal]
    ) -> float:
        """计算融合决策的置信度"""
        # 基础置信度
        base_confidence = 0.5

        # 价格信号确定性
        if price_action in [DecisionAction.EXIT_IMMEDIATELY, DecisionAction.NO_ACTION]:
            base_confidence += 0.2
        else:
            base_confidence += 0.1

        # 资金流信号置信度
        base_confidence += flow_confidence * 0.2

        # 信号一致性奖励
        price_negative = price_action in [
            DecisionAction.EXIT_IMMEDIATELY,
            DecisionAction.ACCELERATE_EXIT
        ]
        flow_negative = flow_action in [
            DecisionAction.EXIT_IMMEDIATELY,
            DecisionAction.ACCELERATE_EXIT
        ]

        if price_negative == flow_negative:
            base_confidence += 0.1  # 信号一致奖励

        # 根据信号数量调整
        if len(flow_signals) >= 2:
            base_confidence += 0.05

        return min(0.99, max(0.1, base_confidence))

    def _calculate_exit_ratio(
        self,
        action: DecisionAction,
        fused_score: float
    ) -> float:
        """计算建议退出比例"""
        ratios = {
            DecisionAction.EXIT_IMMEDIATELY: 1.0,
            DecisionAction.ACCELERATE_EXIT: 0.6 + abs(fused_score) * 0.2,
            DecisionAction.HOLD_WITH_CAUTION: 0.2,
            DecisionAction.NO_ACTION: 0.0,
            DecisionAction.DELAY_EXIT: 0.0,
        }
        return ratios.get(action, 0.0)

    def _apply_extreme_override(
        self,
        current_action: DecisionAction,
        price_signal: Optional[Dict],
        flow_signals: List[FlowSignal]
    ) -> DecisionAction:
        """
        应用极端情况覆盖规则

        极端情况：
        1. 价格触发止损 + 资金流负向 => 立即退出
        2. 资金流极端负向 (> 3σ) => 立即退出
        3. 价格未触发 + 资金流强正向 => 推迟退出
        """
        # 检查价格信号
        price_is_stop_loss = price_signal and "stop_loss" in price_signal.get("type", "").lower()
        price_is_take_profit = price_signal and "take_profit" in price_signal.get("type", "").lower()

        # 分析资金流信号
        has_extreme_negative = any(
            s.direction == FlowDirection.NEGATIVE and
            s.strength == SignalStrength.EXTREME
            for s in flow_signals
        )

        has_strong_negative = any(
            s.direction == FlowDirection.NEGATIVE and
            s.strength.value >= SignalStrength.STRONG.value
            for s in flow_signals
        )

        has_strong_positive = any(
            s.direction == FlowDirection.POSITIVE and
            s.strength.value >= SignalStrength.STRONG.value
            for s in flow_signals
        )

        # 极端情况覆盖规则
        if price_is_stop_loss and has_strong_negative:
            # 价格止损 + 资金流负向 = 立即退出
            self._stats["extreme_overrides"] += 1
            logger.warning("Extreme override: Price stop-loss + negative flow = EXIT_IMMEDIATELY")
            return DecisionAction.EXIT_IMMEDIATELY

        if has_extreme_negative:
            # 极端负向资金流 = 立即退出
            self._stats["extreme_overrides"] += 1
            logger.warning("Extreme override: Extreme negative flow detected = EXIT_IMMEDIATELY")
            return DecisionAction.EXIT_IMMEDIATELY

        if price_is_take_profit and has_strong_positive:
            # 价格止盈 + 资金流正向 = 推迟退出（等待更高点）
            self._stats["extreme_overrides"] += 1
            logger.info("Extreme override: Price take-profit + positive flow = DELAY_EXIT")
            return DecisionAction.DELAY_EXIT

        return current_action

    def _assess_risk_factors(
        self,
        price_signal: Optional[Dict],
        flow_signals: List[FlowSignal],
        final_action: DecisionAction
    ) -> List[str]:
        """评估风险因素"""
        risks = []

        # 价格信号风险
        if price_signal:
            signal_type = price_signal.get("type", "")
            if "stop_loss" in signal_type:
                risks.append("价格已触发止损位")
            elif "take_profit" in signal_type:
                risks.append("价格已触发止盈位")

        # 资金流风险
        negative_signals = [s for s in flow_signals if s.direction == FlowDirection.NEGATIVE]
        if negative_signals:
            strongest = max(negative_signals, key=lambda s: s.strength.value)
            risks.append(f"检测到{strongest.strength.name}负向资金流信号")

        # 决策风险
        if final_action == DecisionAction.EXIT_IMMEDIATELY:
            risks.append("决策为立即退出，可能存在追跌风险")
        elif final_action == DecisionAction.DELAY_EXIT:
            risks.append("决策为推迟退出，可能错过最佳退出时机")

        return risks

    def _update_stats(
        self,
        price_action: DecisionAction,
        flow_action: DecisionAction,
        final_action: DecisionAction
    ) -> None:
        """更新统计信息"""
        self._stats["total_decisions"] += 1

        if price_action != DecisionAction.NO_ACTION:
            self._stats["price_based_decisions"] += 1

        if flow_action != DecisionAction.NO_ACTION:
            self._stats["flow_based_decisions"] += 1

        if price_action != DecisionAction.NO_ACTION and flow_action != DecisionAction.NO_ACTION:
            self._stats["fused_decisions"] += 1

    def get_decision_history(
        self,
        position_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取决策历史"""
        history = list(self._decision_history)

        if position_id:
            history = [h for h in history if h["position_id"] == position_id]

        return [h["result"].__dict__ for h in history[-limit:]]

    def get_stats(self) -> Dict:
        """获取决策引擎统计"""
        return {
            **self._stats,
            "weights": self.weights,
            "confidence_threshold": self.confidence_threshold,
            "enable_extreme_override": self.enable_extreme_override,
            "history_size": len(self._decision_history),
        }


# =============================================================================
# 4. 统计和报告模块 (FlowAnalytics)
# =============================================================================

class FlowAnalytics:
    """
    统计和报告模块

    提供完整的资金流分析统计和报告功能：
    - 检测准确率统计（真阳性、假阳性、真阴性、假阴性）
    - 资金流失效分析（何时信号有效，何时无效）
    - 历史回测报告（基于历史数据验证策略效果）
    - 实时监控面板（当前资金流状态、信号强度）
    """

    def __init__(
        self,
        performance_window: int = 1000,
        backtest_enabled: bool = True,
        realtime_dashboard: bool = True
    ):
        """
        初始化统计和报告模块

        Args:
            performance_window: 性能统计窗口大小
            backtest_enabled: 是否启用回测功能
            realtime_dashboard: 是否启用实时监控面板
        """
        self.performance_window = performance_window
        self.backtest_enabled = backtest_enabled
        self.realtime_dashboard = realtime_dashboard

        # 性能指标统计
        self._performance = PerformanceMetrics()

        # 信号历史记录
        self._signal_history: deque = deque(maxlen=performance_window)

        # 决策历史记录
        self._decision_history: deque = deque(maxlen=performance_window)

        # 回测数据
        self._backtest_data: List[Dict] = []

        # 实时监控数据
        self._realtime_metrics: Dict = {}
        self._last_update: datetime = datetime.now()

        # 失效分析统计
        self._failure_analysis = {
            "signal_types": {},
            "market_conditions": {},
            "time_patterns": {},
        }

        logger.info(
            f"FlowAnalytics initialized: "
            f"performance_window={performance_window}, "
            f"backtest_enabled={backtest_enabled}"
        )

    def record_prediction(
        self,
        prediction: Dict,
        actual_outcome: bool,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        记录预测结果用于准确率统计

        Args:
            prediction: 预测信息
            actual_outcome: 实际结果 (True = 预测正确)
            metadata: 额外元数据
        """
        self._performance.total_predictions += 1

        predicted_positive = prediction.get("is_positive", False)

        if predicted_positive and actual_outcome:
            self._performance.true_positives += 1
        elif predicted_positive and not actual_outcome:
            self._performance.false_positives += 1
        elif not predicted_positive and actual_outcome:
            self._performance.false_negatives += 1
        else:
            self._performance.true_negatives += 1

        # 记录历史
        record = {
            "timestamp": datetime.now(),
            "prediction": prediction,
            "actual_outcome": actual_outcome,
            "is_correct": (predicted_positive == actual_outcome),
            "metadata": metadata or {}
        }
        self._performance.prediction_history.append(record)

        # 更新准确率趋势
        if len(self._performance.prediction_history) >= 10:
            recent = self._performance.prediction_history[-10:]
            accuracy = sum(1 for r in recent if r["is_correct"]) / 10
            self._performance.accuracy_trend.append(accuracy)

    def record_signal(self, signal: FlowSignal, outcome: Optional[str] = None) -> None:
        """记录信号及其结果"""
        record = {
            "timestamp": signal.timestamp,
            "signal": signal,
            "outcome": outcome,
            "recorded_at": datetime.now()
        }
        self._signal_history.append(record)

    def record_decision(self, result: DecisionResult, actual_pnl: Optional[float] = None) -> None:
        """记录决策及其实际结果"""
        record = {
            "timestamp": result.timestamp,
            "decision": result,
            "actual_pnl": actual_pnl,
            "recorded_at": datetime.now()
        }
        self._decision_history.append(record)

    def analyze_signal_effectiveness(
        self,
        signal_type: Optional[str] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> Dict:
        """
        分析信号有效性

        Args:
            signal_type: 信号类型筛选
            time_range: 时间范围筛选

        Returns:
            有效性分析报告
        """
        # 筛选记录
        records = list(self._signal_history)

        if signal_type:
            records = [r for r in records if r["signal"].signal_type == signal_type]

        if time_range:
            start, end = time_range
            records = [r for r in records if start <= r["timestamp"] <= end]

        if not records:
            return {"error": "No records found for the given criteria"}

        # 统计有效性
        outcomes = {"correct": 0, "incorrect": 0, "unknown": 0}
        strength_effectiveness = {s: {"correct": 0, "total": 0} for s in SignalStrength}

        for record in records:
            outcome = record.get("outcome", "unknown")
            signal = record["signal"]

            if outcome == "correct":
                outcomes["correct"] += 1
                strength_effectiveness[signal.strength]["correct"] += 1
            elif outcome == "incorrect":
                outcomes["incorrect"] += 1
            else:
                outcomes["unknown"] += 1

            strength_effectiveness[signal.strength]["total"] += 1

        total_with_outcome = outcomes["correct"] + outcomes["incorrect"]
        overall_accuracy = (
            outcomes["correct"] / total_with_outcome
            if total_with_outcome > 0 else 0.0
        )

        # 各强度有效性
        strength_accuracy = {}
        for strength, stats in strength_effectiveness.items():
            if stats["total"] > 0:
                strength_accuracy[strength.name] = stats["correct"] / stats["total"]

        return {
            "total_records": len(records),
            "outcomes": outcomes,
            "overall_accuracy": overall_accuracy,
            "strength_accuracy": strength_accuracy,
            "by_signal_type": self._group_by_signal_type(records),
        }

    def _group_by_signal_type(self, records: List[Dict]) -> Dict:
        """按信号类型分组统计"""
        groups = {}
        for record in records:
            sig_type = record["signal"].signal_type
            if sig_type not in groups:
                groups[sig_type] = {"total": 0, "correct": 0}
            groups[sig_type]["total"] += 1
            if record.get("outcome") == "correct":
                groups[sig_type]["correct"] += 1

        # 计算准确率
        for sig_type, stats in groups.items():
            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0

        return groups

    def generate_backtest_report(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict:
        """
        生成回测报告

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            回测报告
        """
        if not self.backtest_enabled:
            return {"error": "Backtest not enabled"}

        # 筛选决策记录
        decisions = list(self._decision_history)

        if start_time:
            decisions = [d for d in decisions if d["timestamp"] >= start_time]
        if end_time:
            decisions = [d for d in decisions if d["timestamp"] <= end_time]

        if not decisions:
            return {"error": "No decision data available for the period"}

        # 统计指标
        total_decisions = len(decisions)
        action_distribution = {}
        pnl_by_action = {}
        correct_predictions = 0

        for d in decisions:
            decision = d["decision"]
            action = decision.action
            actual_pnl = d.get("actual_pnl")

            # 行动分布
            action_distribution[action.value] = action_distribution.get(action.value, 0) + 1

            # 按行动统计P&L
            if actual_pnl is not None:
                if action.value not in pnl_by_action:
                    pnl_by_action[action.value] = []
                pnl_by_action[action.value].append(actual_pnl)

            # 预测正确性
            if self._is_correct_prediction(decision, actual_pnl):
                correct_predictions += 1

        # 计算平均P&L
        avg_pnl_by_action = {
            action: np.mean(pnls) if pnls else 0
            for action, pnls in pnl_by_action.items()
        }

        # 预测准确率
        prediction_accuracy = correct_predictions / total_decisions if total_decisions > 0 else 0

        return {
            "period": {
                "start": min(d["timestamp"] for d in decisions),
                "end": max(d["timestamp"] for d in decisions),
            },
            "total_decisions": total_decisions,
            "action_distribution": action_distribution,
            "prediction_accuracy": prediction_accuracy,
            "pnl_statistics": {
                "by_action": avg_pnl_by_action,
                "overall_avg": np.mean([p for pnls in pnl_by_action.values() for p in pnls]) if pnl_by_action else 0
            },
            "sample_decisions": [
                {
                    "timestamp": d["timestamp"],
                    "action": d["decision"].action.value,
                    "confidence": d["decision"].confidence,
                    "actual_pnl": d.get("actual_pnl")
                }
                for d in decisions[:5]  # 前5个样本
            ]
        }

    def _is_correct_prediction(self, decision: DecisionResult, actual_pnl: Optional[float]) -> bool:
        """判断预测是否正确"""
        if actual_pnl is None:
            return False

        # 如果建议退出且实际亏损减少/盈利增加，则正确
        if decision.action in [DecisionAction.EXIT_IMMEDIATELY, DecisionAction.ACCELERATE_EXIT]:
            return actual_pnl >= -0.05  # 亏损不超过5%算正确

        # 如果建议持有且实际盈利，则正确
        if decision.action in [DecisionAction.HOLD_WITH_CAUTION, DecisionAction.DELAY_EXIT]:
            return actual_pnl > 0

        return True

    def get_realtime_dashboard(self) -> Dict:
        """
        获取实时监控面板数据

        Returns:
            实时监控面板数据
        """
        if not self.realtime_dashboard:
            return {"error": "Realtime dashboard not enabled"}

        return {
            "timestamp": datetime.now(),
            "performance": {
                "accuracy": self._performance.accuracy,
                "precision": self._performance.precision,
                "recall": self._performance.recall,
                "f1_score": self._performance.f1_score,
                "total_predictions": self._performance.total_predictions,
            },
            "recent_signals": [
                {
                    "timestamp": s["timestamp"],
                    "type": s["signal"].signal_type,
                    "direction": s["signal"].direction.value,
                    "strength": s["signal"].strength.name,
                }
                for s in list(self._signal_history)[-10:]
            ],
            "recent_decisions": [
                {
                    "timestamp": d["timestamp"],
                    "position_id": d["decision"].position_id,
                    "action": d["decision"].action.value,
                    "confidence": d["decision"].confidence,
                }
                for d in list(self._decision_history)[-10:]
            ],
            "accuracy_trend": self._performance.accuracy_trend[-20:] if self._performance.accuracy_trend else [],
        }

    def get_performance_summary(self) -> Dict:
        """获取性能摘要"""
        return {
            "predictions": {
                "total": self._performance.total_predictions,
                "true_positives": self._performance.true_positives,
                "false_positives": self._performance.false_positives,
                "true_negatives": self._performance.true_negatives,
                "false_negatives": self._performance.false_negatives,
            },
            "metrics": {
                "accuracy": self._performance.accuracy,
                "precision": self._performance.precision,
                "recall": self._performance.recall,
                "f1_score": self._performance.f1_score,
            },
            "data_volumes": {
                "signal_history": len(self._signal_history),
                "decision_history": len(self._decision_history),
                "accuracy_trend_points": len(self._performance.accuracy_trend),
            }
        }

    def reset_performance_metrics(self) -> None:
        """重置性能指标"""
        self._performance = PerformanceMetrics()
        logger.info("Performance metrics reset")


# =============================================================================
# 集成类：资金流辅助止盈止损系统
# =============================================================================

class CapitalFlowAssistedExit:
    """
    资金流辅助止盈止损系统 (主入口类)

    集成四个核心模块：
    1. CapitalFlowCollector - 资金流数据收集
    2. FlowSignalCalculator - 信号计算
    3. FlowAssistedDecision - 辅助决策
    4. FlowAnalytics - 统计报告

    使用示例：
        # 初始化
        exit_system = CapitalFlowAssistedExit()

        # 添加交易数据
        exit_system.add_trade(timestamp, price, size, side)

        # 检查是否应退出
        result = exit_system.check_exit_conditions(
            position_id="pos_123",
            entry_price=0.5,
            current_price=0.6,
            price_signal={"type": "take_profit"}
        )

        if result.action == DecisionAction.EXIT_IMMEDIATELY:
            print(f"建议立即退出，置信度: {result.confidence:.1%}")
    """

    def __init__(
        self,
        config: Optional[Dict] = None,
        collector_config: Optional[Dict] = None,
        calculator_config: Optional[Dict] = None,
        decision_config: Optional[Dict] = None,
        analytics_config: Optional[Dict] = None
    ):
        """
        初始化资金流辅助退出系统

        Args:
            config: 全局配置
            collector_config: 数据收集器配置
            calculator_config: 信号计算器配置
            decision_config: 决策引擎配置
            analytics_config: 分析模块配置
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

        # 初始化四个核心模块
        self.collector = CapitalFlowCollector(**(collector_config or {}))
        self.calculator = FlowSignalCalculator(**(calculator_config or {}))
        self.decision = FlowAssistedDecision(**(decision_config or {}))
        self.analytics = FlowAnalytics(**(analytics_config or {}))

        # 持仓跟踪
        self._positions: Dict[str, Dict] = {}

        logger.info(
            f"CapitalFlowAssistedExit initialized: enabled={self.enabled}, "
            f"modules=[collector, calculator, decision, analytics]"
        )

    def add_trade(
        self,
        timestamp: Union[datetime, float],
        price: float,
        size: float,
        side: str,
        trader_id: Optional[str] = None
    ) -> None:
        """
        添加交易数据

        Args:
            timestamp: 时间戳
            price: 成交价格
            size: 成交量
            side: 方向 ("buy" 或 "sell")
            trader_id: 交易者ID
        """
        if not self.enabled:
            return

        # 添加到收集器
        self.collector.add_trade(timestamp, price, size, side, trader_id)

        # 同时更新计算器的分钟流数据
        if isinstance(timestamp, (int, float)):
            ts = datetime.fromtimestamp(timestamp)
        else:
            ts = timestamp

        # 分钟级聚合（简化处理）
        net_flow = size if side.lower() == "buy" else -size
        self.calculator.add_minute_flow(ts, net_flow)

    def add_trades_batch(self, trades: List[Dict]) -> None:
        """批量添加交易数据"""
        for trade in trades:
            self.add_trade(
                timestamp=trade.get("timestamp", datetime.now()),
                price=trade["price"],
                size=trade["size"],
                side=trade["side"],
                trader_id=trade.get("trader_id")
            )

    def register_position(
        self,
        position_id: str,
        entry_price: float,
        size: float,
        side: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        注册持仓以进行跟踪

        Args:
            position_id: 持仓ID
            entry_price: 入场价格
            size: 持仓数量
            side: 持仓方向 ("long" 或 "short")
            metadata: 额外元数据
        """
        self._positions[position_id] = {
            "position_id": position_id,
            "entry_price": entry_price,
            "size": size,
            "side": side,
            "entry_time": datetime.now(),
            "metadata": metadata or {}
        }

        logger.debug(f"Position registered for flow tracking: {position_id}")

    def check_exit_conditions(
        self,
        position_id: str,
        current_price: float,
        price_signal: Optional[Dict] = None,
        extra_context: Optional[Dict] = None
    ) -> DecisionResult:
        """
        检查退出条件并做出决策

        Args:
            position_id: 持仓ID
            current_price: 当前价格
            price_signal: 价格信号（如止盈止损触发）
            extra_context: 额外上下文

        Returns:
            DecisionResult: 决策结果
        """
        if not self.enabled:
            # 如果禁用，返回无操作
            return DecisionResult(
                timestamp=datetime.now(),
                position_id=position_id,
                price_signal=price_signal,
                flow_signal=None,
                action=DecisionAction.NO_ACTION,
                exit_ratio=0.0,
                confidence=0.0,
                reasoning=["资金流辅助决策已禁用"],
                risk_factors=[],
                weights_snapshot=self.decision.weights
            )

        # 获取持仓信息
        position = self._positions.get(position_id, {})
        entry_price = position.get("entry_price", current_price)

        # 计算当前利润
        profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

        # 计算资金流信号
        flow_signals = self.calculator.calculate_signals()

        # 构建上下文
        context = {
            "position_id": position_id,
            "entry_price": entry_price,
            "current_price": current_price,
            "profit_pct": profit_pct,
            "position_side": position.get("side", "long"),
            **(extra_context or {})
        }

        # 做出决策
        result = self.decision.make_decision(
            position_id=position_id,
            price_signal=price_signal,
            flow_signals=flow_signals,
            context=context
        )

        # 记录到分析模块
        self.analytics.record_decision(result, actual_pnl=None)
        for signal in flow_signals:
            self.analytics.record_signal(signal)

        return result

    def get_flow_metrics(self, window_seconds: Optional[int] = None) -> FlowMetrics:
        """获取资金流指标"""
        return self.collector.get_flow_metrics(window_seconds)

    def get_multi_window_metrics(self) -> Dict[int, FlowMetrics]:
        """获取多窗口资金流指标"""
        return self.collector.get_multi_window_metrics()

    def get_realtime_dashboard(self) -> Dict:
        """获取实时监控面板数据"""
        return {
            "timestamp": datetime.now(),
            "flow_metrics": {
                window: {
                    "net_flow": m.net_flow,
                    "inflow": m.inflow,
                    "outflow": m.outflow,
                    "unique_traders": m.total_unique_traders,
                    "price_change_pct": m.price_change_pct,
                }
                for window, m in self.get_multi_window_metrics().items()
            },
            "recent_signals": [
                {
                    "timestamp": s["timestamp"],
                    "type": s["signal"].signal_type,
                    "direction": s["signal"].direction.value,
                    "strength": s["signal"].strength.name,
                }
                for s in list(self.analytics._signal_history)[-10:]
            ],
            "performance": self.analytics.get_performance_summary()["metrics"],
            "system_status": {
                "enabled": self.enabled,
                "collector_stats": self.collector.get_stats(),
                "calculator_stats": self.calculator.get_stats(),
                "decision_stats": self.decision.get_stats(),
            }
        }

    def generate_analytics_report(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict:
        """
        生成综合分析报告

        Args:
            start_time: 报告开始时间
            end_time: 报告结束时间

        Returns:
            综合分析报告
        """
        now = datetime.now()
        start_time = start_time or (now - timedelta(days=7))
        end_time = end_time or now

        return {
            "report_period": {
                "start": start_time,
                "end": end_time,
            },
            "performance_summary": self.analytics.get_performance_summary(),
            "signal_effectiveness": self.analytics.analyze_signal_effectiveness(
                time_range=(start_time, end_time)
            ),
            "backtest_report": self.analytics.generate_backtest_report(
                start_time, end_time
            ) if self.backtest_enabled else {"enabled": False},
            "realtime_metrics": self.get_realtime_dashboard(),
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []

        # 基于性能指标的建议
        perf = self.analytics.get_performance_summary()
        metrics = perf["metrics"]

        if metrics["accuracy"] < 0.6:
            recommendations.append("整体准确率偏低，建议调整权重配置或信号阈值")

        if metrics["precision"] < 0.5:
            recommendations.append("精确率较低，建议提高信号触发阈值以减少假阳性")

        if metrics["recall"] < 0.5:
            recommendations.append("召回率较低，建议降低信号阈值以捕获更多有效信号")

        # 基于信号有效性的建议
        effectiveness = self.analytics.analyze_signal_effectiveness()
        if "by_signal_type" in effectiveness:
            for sig_type, stats in effectiveness["by_signal_type"].items():
                if stats.get("accuracy", 1.0) < 0.5:
                    recommendations.append(f"{sig_type}信号表现较差，建议优化或降低权重")

        if not recommendations:
            recommendations.append("当前配置表现良好，建议维持现有参数")

        return recommendations

    def get_stats(self) -> Dict:
        """获取系统整体统计"""
        return {
            "enabled": self.enabled,
            "positions_tracked": len(self._positions),
            "modules": {
                "collector": self.collector.get_stats(),
                "calculator": self.calculator.get_stats(),
                "decision": self.decision.get_stats(),
                "analytics": self.analytics.get_performance_summary(),
            }
        }


# =============================================================================
# 便捷函数
# =============================================================================

def create_default_system(
    enabled: bool = True,
    custom_weights: Optional[Dict[str, float]] = None
) -> CapitalFlowAssistedExit:
    """
    创建默认配置的资金流辅助退出系统

    Args:
        enabled: 是否启用
        custom_weights: 自定义权重

    Returns:
        CapitalFlowAssistedExit 实例
    """
    config = {"enabled": enabled}

    decision_config = {
        "weights": custom_weights or {
            "price_based_exit": 0.7,
            "flow_acceleration": 0.3,
        },
        "confidence_threshold": 0.6,
        "enable_extreme_override": True,
    }

    return CapitalFlowAssistedExit(
        config=config,
        decision_config=decision_config
    )
