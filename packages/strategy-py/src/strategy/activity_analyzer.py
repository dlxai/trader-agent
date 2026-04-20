#!/usr/bin/env python3
"""
WebSocket Activity 综合分析器

整合功能：
1. 交易员画像 - 跟踪大户习惯、胜率
2. 市场热度 - 统计每个市场的活跃度
3. 价格波动 - 实时价格变化率
4. 异常检测 - 突然大单、密集交易
5. 多市场关联 - 相关市场同时活跃

使用方式：
    from polymarket_sdk.services.activity_analyzer import ActivityAnalyzer

    analyzer = ActivityAnalyzer()
    analyzer.process_trade(trade_data)

    # 获取分析结果
    hot_markets = analyzer.get_hot_markets(limit=10)
    top_traders = analyzer.get_top_traders(limit=10)
    anomalies = analyzer.get_anomalies()
"""
import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import statistics

logger = logging.getLogger(__name__)


@dataclass
class TraderProfile:
    """交易员画像"""

    address: str
    total_trades: int = 0
    total_volume: float = 0.0
    markets_traded: Set[str] = field(default_factory=set)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    outcomes: Dict[str, int] = field(default_factory=lambda: defaultdict(int))  # YES/NO 计数

    # 跟踪交易习惯
    avg_trade_size: float = 0.0
    trade_sizes: List[float] = field(default_factory=list)

    # 胜率跟踪（需要有结果的市场）
    positions: List[Dict] = field(default_factory=list)  # {market, side, entry_price, entry_time}

    @property
    def trade_frequency(self) -> float:
        """交易频率（每小时）"""
        age_hours = max((self.last_seen - self.first_seen) / 3600, 0.01)
        return self.total_trades / age_hours

    @property
    def is_whale(self) -> bool:
        """是否为大户（单笔平均 > $100）"""
        return self.avg_trade_size > 100

    @property
    def preferred_outcome(self) -> str:
        """偏好方向"""
        if not self.outcomes:
            return "UNKNOWN"
        return max(self.outcomes.items(), key=lambda x: x[1])[0]

    def add_trade(self, trade: Dict):
        """添加一笔交易"""
        self.total_trades += 1
        amount = trade.get("amount", 0)
        self.total_volume += amount
        self.trade_sizes.append(amount)
        self.avg_trade_size = sum(self.trade_sizes) / len(self.trade_sizes)

        condition_id = trade.get("condition_id")
        if condition_id:
            self.markets_traded.add(condition_id)

        outcome = trade.get("outcome", "UNKNOWN")
        self.outcomes[outcome] += 1

        self.last_seen = time.time()


@dataclass
class MarketActivity:
    """市场活跃度"""

    condition_id: str
    slug: str
    question: str

    # 基础统计
    total_trades: int = 0
    unique_traders: Set[str] = field(default_factory=set)
    total_volume: float = 0.0
    yes_volume: float = 0.0
    no_volume: float = 0.0

    # 价格跟踪
    prices: deque = field(default_factory=lambda: deque(maxlen=100))
    current_price: float = 0.5
    price_change_1m: float = 0.0
    price_change_5m: float = 0.0

    # 时间跟踪
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    recent_trades: deque = field(default_factory=lambda: deque(maxlen=50))

    # 热度评分
    activity_score: float = 0.0

    @property
    def age_minutes(self) -> float:
        """市场被跟踪的分钟数"""
        return (self.last_seen - self.first_seen) / 60

    @property
    def trader_count(self) -> int:
        """独立交易员数量"""
        return len(self.unique_traders)

    @property
    def avg_trade_size(self) -> float:
        """平均交易规模"""
        return self.total_volume / max(self.total_trades, 1)

    @property
    def net_flow(self) -> float:
        """净流入（YES - NO）"""
        return self.yes_volume - self.no_volume

    @property
    def yes_ratio(self) -> float:
        """YES 资金占比"""
        total = self.yes_volume + self.no_volume
        return self.yes_volume / max(total, 1)

    @property
    def volatility_1m(self) -> float:
        """1分钟波动率"""
        if len(self.prices) < 2:
            return 0.0
        recent = list(self.prices)[-10:]  # 最近10个价格点
        if len(recent) < 2:
            return 0.0
        return statistics.stdev(recent) if len(recent) > 1 else 0.0

    def add_trade(self, trade: Dict):
        """添加一笔交易"""
        self.total_trades += 1
        self.last_seen = time.time()

        trader = trade.get("trader_address")
        if trader:
            self.unique_traders.add(trader)

        amount = trade.get("amount", 0)
        side = trade.get("side", "BUY")
        outcome = trade.get("outcome", "YES")

        self.total_volume += amount
        if outcome == "YES":
            self.yes_volume += amount
        else:
            self.no_volume += amount

        price = trade.get("price", 0.5)
        self.current_price = price
        self.prices.append(price)

        # 记录最近交易
        self.recent_trades.append(
            {
                "time": time.time(),
                "trader": trader,
                "amount": amount,
                "side": side,
                "outcome": outcome,
                "price": price,
            }
        )

        # 更新热度评分
        self._update_score()

    def _update_score(self):
        """计算热度评分"""
        # 综合考虑：交易量、交易员数、交易频率
        volume_score = min(self.total_volume / 1000, 1.0)  # $1000 满分
        trader_score = min(self.trader_count / 10, 1.0)  # 10个交易员满分
        frequency_score = min(self.total_trades / 50, 1.0)  # 50笔交易满分

        # 时间衰减（最近的活动权重更高）
        time_factor = 1.0
        if self.age_minutes > 5:
            time_factor = max(0.5, 1 - (self.age_minutes - 5) / 60)

        self.activity_score = (
            volume_score * 0.4 + trader_score * 0.3 + frequency_score * 0.3
        ) * time_factor


@dataclass
class Anomaly:
    """异常事件"""

    type: str  # 'large_trade', 'activity_spike', 'price_jump', 'whale_accumulation'
    condition_id: str
    market_slug: str
    severity: float  # 0-1
    timestamp: float
    details: Dict

    def __str__(self):
        return f"[{self.type}] {self.market_slug[:30]}... (severity={self.severity:.2f})"


class ActivityAnalyzer:
    """
    WebSocket Activity 综合分析器

    功能：
    1. 交易员画像 - 跟踪大户
    2. 市场热度 - 排行榜
    3. 价格波动 - 动量检测
    4. 异常检测 - 突发事件
    5. 多市场关联 - 趋势确认
    """

    def __init__(
        self, max_traders: int = 1000, max_markets: int = 500, anomaly_threshold: float = 2.0
    ):
        """
        Args:
            max_traders: 最大跟踪交易员数
            max_markets: 最大跟踪市场数
            anomaly_threshold: 异常检测阈值（标准差倍数）
        """
        # 交易员跟踪
        self.traders: Dict[str, TraderProfile] = {}
        self.max_traders = max_traders

        # 市场跟踪
        self.markets: Dict[str, MarketActivity] = {}
        self.max_markets = max_markets

        # 异常检测
        self.anomalies: List[Anomaly] = []
        self.anomaly_threshold = anomaly_threshold

        # 价格历史（用于动量计算）
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # 统计
        self.total_trades_processed = 0
        self.start_time = time.time()

        # 回调
        self._anomaly_callbacks = []
        self._hot_market_callbacks = []

        logger.info("[ActivityAnalyzer] 初始化完成")

    # ========================================================================
    # 核心处理
    # ========================================================================

    def process_trade(self, trade: Dict) -> Optional[Anomaly]:
        """
        处理单笔交易

        Args:
            trade: 交易数据字典

        Returns:
            如果检测到异常，返回 Anomaly 对象
        """
        self.total_trades_processed += 1

        condition_id = trade.get("condition_id")
        if not condition_id:
            return None

        # 1. 更新交易员画像
        self._update_trader(trade)

        # 2. 更新市场活跃度
        market_activity = self._update_market(trade)

        # 3. 检测异常
        anomaly = self._detect_anomalies(trade, market_activity)
        if anomaly:
            self.anomalies.append(anomaly)
            # 清理旧异常
            if len(self.anomalies) > 100:
                self.anomalies = self.anomalies[-50:]
            # 触发回调
            for callback in self._anomaly_callbacks:
                try:
                    callback(anomaly)
                except:
                    pass

        # 4. 检测市场热度变化
        if market_activity and market_activity.activity_score > 0.7:
            for callback in self._hot_market_callbacks:
                try:
                    callback(market_activity)
                except:
                    pass

        return anomaly

    def _update_trader(self, trade: Dict):
        """更新交易员画像"""
        trader_addr = trade.get("trader_address")
        if not trader_addr:
            return

        if trader_addr not in self.traders:
            if len(self.traders) >= self.max_traders:
                # 移除最久活跃的交易员
                oldest = min(self.traders.items(), key=lambda x: x[1].last_seen)
                del self.traders[oldest[0]]

            self.traders[trader_addr] = TraderProfile(address=trader_addr)

        self.traders[trader_addr].add_trade(trade)

    def _update_market(self, trade: Dict) -> Optional[MarketActivity]:
        """更新市场活跃度"""
        condition_id = trade.get("condition_id")
        if not condition_id:
            return None

        if condition_id not in self.markets:
            if len(self.markets) >= self.max_markets:
                # 移除最久活跃的市场
                oldest = min(self.markets.items(), key=lambda x: x[1].last_seen)
                del self.markets[oldest[0]]

            self.markets[condition_id] = MarketActivity(
                condition_id=condition_id,
                slug=trade.get("slug", ""),
                question=trade.get("title", ""),
            )

        self.markets[condition_id].add_trade(trade)
        return self.markets[condition_id]

    def _detect_anomalies(self, trade: Dict, market: MarketActivity) -> Optional[Anomaly]:
        """检测异常事件"""
        condition_id = trade.get("condition_id", "")
        slug = trade.get("slug", "")
        now = time.time()

        # 1. 大单检测
        amount = trade.get("amount", 0)
        avg_size = market.avg_trade_size if market else 0
        if avg_size > 0 and amount > avg_size * 10:
            return Anomaly(
                type="large_trade",
                condition_id=condition_id,
                market_slug=slug,
                severity=min(amount / 1000, 1.0),
                timestamp=now,
                details={
                    "amount": amount,
                    "avg_size": avg_size,
                    "ratio": amount / max(avg_size, 1),
                },
            )

        # 2. 活动激增检测
        if market and market.total_trades > 20:
            recent_trades = [t for t in market.recent_trades if now - t["time"] < 60]  # 最近1分钟
            if len(recent_trades) > 10:
                # 计算交易速率
                rate = len(recent_trades)
                if rate > 20:  # 1分钟内超过20笔
                    return Anomaly(
                        type="activity_spike",
                        condition_id=condition_id,
                        market_slug=slug,
                        severity=min(rate / 50, 1.0),
                        timestamp=now,
                        details={"trades_per_minute": rate},
                    )

        # 3. 价格跳跃检测
        if market and len(market.prices) >= 5:
            recent_prices = list(market.prices)[-5:]
            price_change = abs(recent_prices[-1] - recent_prices[0])
            if price_change > 0.05:  # 5% 以上变化
                return Anomaly(
                    type="price_jump",
                    condition_id=condition_id,
                    market_slug=slug,
                    severity=min(price_change / 0.2, 1.0),
                    timestamp=now,
                    details={
                        "change": price_change,
                        "from_price": recent_prices[0],
                        "to_price": recent_prices[-1],
                    },
                )

        # 4. 大户囤积检测
        trader_addr = trade.get("trader_address")
        if trader_addr and trader_addr in self.traders:
            trader = self.traders[trader_addr]
            if trader.is_whale:
                # 检查这个大户是否在短时间内多次买入同一市场
                recent_trades = [
                    t
                    for t in (market.recent_trades if market else [])
                    if t["trader"] == trader_addr and now - t["time"] < 300
                ]
                if len(recent_trades) >= 3:  # 5分钟内3笔以上
                    total_accumulated = sum(t["amount"] for t in recent_trades)
                    return Anomaly(
                        type="whale_accumulation",
                        condition_id=condition_id,
                        market_slug=slug,
                        severity=min(total_accumulated / 500, 1.0),
                        timestamp=now,
                        details={
                            "whale": trader_addr[:10],
                            "trades": len(recent_trades),
                            "total_amount": total_accumulated,
                        },
                    )

        return None

    # ========================================================================
    # 查询接口
    # ========================================================================

    def get_hot_markets(self, limit: int = 10, min_score: float = 0.3) -> List[MarketActivity]:
        """获取最热门的市场"""
        markets = [m for m in self.markets.values() if m.activity_score >= min_score]
        return sorted(markets, key=lambda x: x.activity_score, reverse=True)[:limit]

    def get_top_traders(self, limit: int = 10, min_volume: float = 100) -> List[TraderProfile]:
        """获取顶级交易员"""
        traders = [t for t in self.traders.values() if t.total_volume >= min_volume]
        return sorted(traders, key=lambda x: x.total_volume, reverse=True)[:limit]

    def get_anomalies(self, limit: int = 20, min_severity: float = 0.5) -> List[Anomaly]:
        """获取最近的异常"""
        cutoff = time.time() - 3600  # 最近1小时
        anomalies = [
            a for a in self.anomalies if a.timestamp >= cutoff and a.severity >= min_severity
        ]
        return sorted(anomalies, key=lambda x: x.timestamp, reverse=True)[:limit]

    def get_whales(self, limit: int = 10) -> List[TraderProfile]:
        """获取大户列表"""
        whales = [t for t in self.traders.values() if t.is_whale]
        return sorted(whales, key=lambda x: x.total_volume, reverse=True)[:limit]

    def get_market_by_condition(self, condition_id: str) -> Optional[MarketActivity]:
        """获取指定市场的活动数据"""
        return self.markets.get(condition_id)

    def get_trader_by_address(self, address: str) -> Optional[TraderProfile]:
        """获取指定交易员的画像"""
        return self.traders.get(address)

    def get_correlated_markets(self, condition_id: str, min_traders: int = 2) -> List[str]:
        """获取关联市场（共享交易员）"""
        if condition_id not in self.markets:
            return []

        target_market = self.markets[condition_id]
        target_traders = target_market.unique_traders

        correlated = []
        for cid, market in self.markets.items():
            if cid == condition_id:
                continue
            # 计算共享交易员数量
            shared = len(target_traders & market.unique_traders)
            if shared >= min_traders:
                correlated.append((cid, shared))

        # 按共享交易员数量排序
        correlated.sort(key=lambda x: x[1], reverse=True)
        return [cid for cid, _ in correlated[:10]]

    # ========================================================================
    # 回调注册
    # ========================================================================

    def on_anomaly(self, callback):
        """注册异常回调"""
        self._anomaly_callbacks.append(callback)

    def on_hot_market(self, callback):
        """注册热门市场回调"""
        self._hot_market_callbacks.append(callback)

    # ========================================================================
    # 统计与调试
    # ========================================================================

    def get_stats(self) -> Dict:
        """获取统计信息"""
        uptime = time.time() - self.start_time

        return {
            "uptime_seconds": uptime,
            "total_trades": self.total_trades_processed,
            "trades_per_second": self.total_trades_processed / max(uptime, 1),
            "tracked_traders": len(self.traders),
            "tracked_markets": len(self.markets),
            "whale_count": sum(1 for t in self.traders.values() if t.is_whale),
            "anomaly_count": len([a for a in self.anomalies if time.time() - a.timestamp < 3600]),
        }

    def get_summary(self) -> str:
        """获取摘要"""
        stats = self.get_stats()
        hot_markets = self.get_hot_markets(limit=5)
        top_traders = self.get_top_traders(limit=5)
        anomalies = self.get_anomalies(limit=5)

        lines = [
            "=" * 60,
            "[ActivityAnalyzer] 实时摘要",
            "=" * 60,
            f"运行时间: {stats['uptime_seconds'] / 60:.1f} 分钟",
            f"处理交易: {stats['total_trades']} 笔 ({stats['trades_per_second']:.1f}/s)",
            f"跟踪交易员: {stats['tracked_traders']} 人 (大户: {stats['whale_count']})",
            f"跟踪市场: {stats['tracked_markets']} 个",
            f"最近异常: {stats['anomaly_count']} 个",
            "",
            "[热门市场 Top 5]",
        ]

        for i, m in enumerate(hot_markets, 1):
            lines.append(
                f"  {i}. {m.question[:40]}... "
                f"(热度:{m.activity_score:.2f}, 交易:{m.total_trades}, "
                f"资金:${m.total_volume:.0f}, 交易员:{m.trader_count})"
            )

        lines.extend(["", "[顶级交易员 Top 5]"])

        for i, t in enumerate(top_traders, 1):
            lines.append(
                f"  {i}. {t.address} "
                f"(交易:{t.total_trades}, 资金:${t.total_volume:.0f}, "
                f"平均:${t.avg_trade_size:.0f}, 偏好:{t.preferred_outcome})"
            )

        if anomalies:
            lines.extend(["", "[最近异常]"])
            for i, a in enumerate(anomalies[:5], 1):
                lines.append(f"  {i}. {a}")

        lines.append("=" * 60)

        return "\n".join(lines)

    def print_summary(self):
        """打印摘要"""
        logger.warning(self.get_summary())
