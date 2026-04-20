"""
信号评估器 - 评估信号质量和历史表现

该模块实现了信号质量评估系统，用于：
- 信号历史回测和表现分析
- 信号质量评分和权重动态调整
- 信号组合优化建议
- 信号准确性、时效性、稳定性评估
"""

import logging
import sqlite3
import json
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Callable, Any, Tuple, Set
from collections import defaultdict
import statistics

# Configure logging
logger = logging.getLogger(__name__)


class SignalQuality(Enum):
    """信号质量等级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNRELIABLE = "unreliable"


class SignalDirection(Enum):
    """信号方向"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NEUTRAL = "neutral"


@dataclass
class SignalRecord:
    """信号记录"""
    signal_id: str
    signal_name: str
    market_id: str
    outcome_id: str
    direction: SignalDirection
    strength: float  # 0-1
    timestamp: datetime

    # 预测信息
    predicted_direction: SignalDirection
    confidence: float
    expected_return: Optional[float] = None
    expected_timeframe: Optional[timedelta] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalOutcome:
    """信号结果"""
    signal_id: str
    market_id: str
    outcome_id: str

    # 实际结果
    actual_direction: SignalDirection
    actual_return: float
    realized_pnl: float

    # 时间信息
    signal_timestamp: datetime
    outcome_timestamp: datetime
    time_to_outcome: timedelta

    # 评估
    prediction_correct: bool
    accuracy_score: float  # 0-1
    profitability_score: float  # 0-1


@dataclass
class SignalMetrics:
    """信号指标"""
    signal_name: str
    total_signals: int

    # 准确性指标
    accuracy: float  # 预测正确率
    precision: float  # 精确率
    recall: float  # 召回率
    f1_score: float  # F1分数

    # 收益指标
    avg_return: float  # 平均回报
    sharpe_ratio: float  # 夏普比率
    max_drawdown: float  # 最大回撤
    win_rate: float  # 胜率
    profit_factor: float  # 盈亏比

    # 时效性指标
    avg_time_to_outcome: timedelta  # 平均达成时间
    signal_latency: timedelta  # 信号延迟

    # 稳定性指标
    consistency_score: float  # 一致性分数
    volatility: float  # 波动性

    # 质量评级
    quality: SignalQuality
    confidence: float  # 置信度

    # 时间戳
    calculated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'signal_name': self.signal_name,
            'total_signals': self.total_signals,
            'accuracy': self.accuracy,
            'precision': self.precision,
            'recall': self.recall,
            'f1_score': self.f1_score,
            'avg_return': self.avg_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'avg_time_to_outcome_seconds': self.avg_time_to_outcome.total_seconds(),
            'signal_latency_seconds': self.signal_latency.total_seconds(),
            'consistency_score': self.consistency_score,
            'volatility': self.volatility,
            'quality': self.quality.value,
            'confidence': self.confidence,
            'calculated_at': self.calculated_at.isoformat()
        }


@dataclass
class SignalEvaluationConfig:
    """信号评估配置"""
    # 数据保留
    max_history_days: int = 90
    min_samples_for_metrics: int = 10

    # 评估周期
    evaluation_window: timedelta = timedelta(days=30)
    update_interval: timedelta = timedelta(hours=1)

    # 质量阈值
    min_accuracy_threshold: float = 0.55  # 最低准确率要求
    min_sharpe_threshold: float = 0.5   # 最低夏普比率
    min_win_rate_threshold: float = 0.45  # 最低胜率

    # 权重调整
    enable_dynamic_weighting: bool = True
    weight_adjustment_factor: float = 0.1  # 每次调整幅度
    max_signal_weight: float = 0.5  # 单个信号最大权重
    min_signal_weight: float = 0.05  # 单个信号最小权重


class SignalEvaluator:
    """信号评估器 - 评估信号质量和历史表现

    评估维度：
    1. 准确性 - 信号预测正确率
    2. 时效性 - 信号到结果的时间
    3. 稳定性 - 信号质量的一致性
    4. 夏普比率 - 风险调整收益

    核心功能：
    - 信号历史回测
    - 信号质量评分
    - 信号权重动态调整
    - 信号组合优化
    """

    def __init__(self, db_connection: Optional[sqlite3.Connection] = None):
        """
        初始化信号评估器

        Args:
            db_connection: SQLite数据库连接，用于持久化数据
        """
        self.db = db_connection
        self.config = SignalEvaluationConfig()

        # 内存缓存
        self._signal_records: Dict[str, SignalRecord] = {}
        self._signal_outcomes: Dict[str, SignalOutcome] = {}
        self._signal_metrics: Dict[str, SignalMetrics] = {}

        # 信号权重
        self._signal_weights: Dict[str, float] = {}

        # 统计数据
        self._stats = {
            'total_evaluations': 0,
            'successful_evaluations': 0,
            'failed_evaluations': 0,
            'last_update': None
        }

        # 初始化数据库
        if self.db:
            self._init_database()

        logger.info("SignalEvaluator initialized")

    def _init_database(self) -> None:
        """初始化数据库表"""
        if not self.db:
            return

        cursor = self.db.cursor()

        # 信号记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signal_records (
                signal_id TEXT PRIMARY KEY,
                signal_name TEXT,
                market_id TEXT,
                outcome_id TEXT,
                direction TEXT,
                strength REAL,
                timestamp TEXT,
                predicted_direction TEXT,
                confidence REAL,
                expected_return REAL,
                metadata TEXT
            )
        ''')

        # 信号结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                signal_id TEXT PRIMARY KEY,
                market_id TEXT,
                outcome_id TEXT,
                actual_direction TEXT,
                actual_return REAL,
                realized_pnl REAL,
                signal_timestamp TEXT,
                outcome_timestamp TEXT,
                time_to_outcome_seconds REAL,
                prediction_correct INTEGER,
                accuracy_score REAL,
                profitability_score REAL
            )
        ''')

        # 信号指标表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signal_metrics (
                signal_name TEXT PRIMARY KEY,
                total_signals INTEGER,
                accuracy REAL,
                precision REAL,
                recall REAL,
                f1_score REAL,
                avg_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                profit_factor REAL,
                consistency_score REAL,
                quality TEXT,
                confidence REAL,
                calculated_at TEXT
            )
        ''')

        self.db.commit()
        logger.info("Signal database initialized")

    async def record_signal(self, signal: SignalRecord) -> None:
        """
        记录信号

        Args:
            signal: 信号记录
        """
        self._signal_records[signal.signal_id] = signal

        # 保存到数据库
        if self.db:
            self._save_signal_to_db(signal)

        logger.debug(f"Signal recorded: {signal.signal_id}")

    def _save_signal_to_db(self, signal: SignalRecord) -> None:
        """保存信号到数据库"""
        cursor = self.db.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO signal_records
            (signal_id, signal_name, market_id, outcome_id, direction, strength,
             timestamp, predicted_direction, confidence, expected_return, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            signal.signal_id,
            signal.signal_name,
            signal.market_id,
            signal.outcome_id,
            signal.direction.value,
            signal.strength,
            signal.timestamp.isoformat(),
            signal.predicted_direction.value,
            signal.confidence,
            signal.expected_return,
            json.dumps(signal.metadata)
        ))
        self.db.commit()

    async def record_outcome(self, outcome: SignalOutcome) -> None:
        """
        记录信号结果

        Args:
            outcome: 信号结果
        """
        self._signal_outcomes[outcome.signal_id] = outcome

        # 保存到数据库
        if self.db:
            self._save_outcome_to_db(outcome)

        # 更新指标
        await self._update_metrics_for_signal(outcome.signal_id)

        logger.debug(f"Outcome recorded for signal: {outcome.signal_id}")

    def _save_outcome_to_db(self, outcome: SignalOutcome) -> None:
        """保存结果到数据库"""
        cursor = self.db.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO signal_outcomes
            (signal_id, market_id, outcome_id, actual_direction, actual_return, realized_pnl,
             signal_timestamp, outcome_timestamp, time_to_outcome_seconds, prediction_correct,
             accuracy_score, profitability_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            outcome.signal_id,
            outcome.market_id,
            outcome.outcome_id,
            outcome.actual_direction.value,
            outcome.actual_return,
            outcome.realized_pnl,
            outcome.signal_timestamp.isoformat(),
            outcome.outcome_timestamp.isoformat(),
            outcome.time_to_outcome.total_seconds(),
            1 if outcome.prediction_correct else 0,
            outcome.accuracy_score,
            outcome.profitability_score
        ))
        self.db.commit()

    async def evaluate_signal(self, signal_id: str) -> Optional[SignalMetrics]:
        """
        评估单个信号

        Args:
            signal_id: 信号ID

        Returns:
            SignalMetrics: 信号指标，如果信号不存在则返回None
        """
        signal = self._signal_records.get(signal_id)
        outcome = self._signal_outcomes.get(signal_id)

        if not signal:
            return None

        if not outcome:
            # 没有结果数据，返回基于置信度的部分指标
            return self._create_partial_metrics(signal)

        # 使用结果计算完整指标
        return await self._calculate_full_metrics(signal, outcome)

    def _create_partial_metrics(self, signal: SignalRecord) -> SignalMetrics:
        """创建部分指标（没有结果数据时）"""
        return SignalMetrics(
            signal_name=signal.signal_name,
            total_signals=1,
            accuracy=signal.confidence,
            precision=signal.confidence,
            recall=0.0,
            f1_score=signal.confidence * 0.5,
            avg_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_time_to_outcome=timedelta(0),
            signal_latency=timedelta(0),
            consistency_score=signal.confidence,
            volatility=0.0,
            quality=SignalQuality.FAIR,
            confidence=signal.confidence,
            calculated_at=datetime.now()
        )

    async def _calculate_full_metrics(self,
                                     signal: SignalRecord,
                                     outcome: SignalOutcome) -> SignalMetrics:
        """计算完整指标"""
        # 获取所有相关信号的历史数据
        signal_history = self._get_signal_history(signal.signal_name)

        if len(signal_history) < self.config.min_samples_for_metrics:
            return self._create_partial_metrics(signal)

        # 计算准确性指标
        total = len(signal_history)
        correct = sum(1 for s, o in signal_history if o.prediction_correct)
        accuracy = correct / total if total > 0 else 0

        # 计算精确率和召回率
        tp = sum(1 for s, o in signal_history
                 if o.prediction_correct and s.direction == SignalDirection.BUY)
        fp = sum(1 for s, o in signal_history
                 if not o.prediction_correct and s.direction == SignalDirection.BUY)
        fn = sum(1 for s, o in signal_history
                 if not o.prediction_correct and s.direction != SignalDirection.BUY)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        # 计算收益指标
        returns = [o.actual_return for _, o in signal_history]
        avg_return = statistics.mean(returns) if returns else 0

        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]

        win_rate = len(wins) / len(returns) if returns else 0

        avg_win = statistics.mean(wins) if wins else 0
        avg_loss = statistics.mean(losses) if losses else 0
        profit_factor = abs(avg_win * len(wins) / (avg_loss * len(losses))) if (avg_loss * len(losses)) != 0 else float('inf')

        # 计算夏普比率（简化版，假设无风险利率为0）
        if len(returns) > 1:
            try:
                volatility = statistics.stdev(returns)
                sharpe = avg_return / volatility if volatility > 0 else 0
            except statistics.StatisticsError:
                volatility = 0
                sharpe = 0
        else:
            volatility = 0
            sharpe = 0

        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown(returns)

        # 计算时效性指标
        times_to_outcome = [o.time_to_outcome for _, o in signal_history]
        avg_time_to_outcome = timedelta(seconds=statistics.mean([t.total_seconds() for t in times_to_outcome])) if times_to_outcome else timedelta(0)

        # 计算稳定性指标
        consistency_scores = [o.accuracy_score for _, o in signal_history]
        consistency_score = statistics.mean(consistency_scores) if consistency_scores else 0

        # 确定质量等级
        quality = self._determine_quality(accuracy, sharpe, win_rate, consistency_score)

        # 计算综合置信度
        confidence = (accuracy + win_rate + consistency_score) / 3

        return SignalMetrics(
            signal_name=signal.signal_name,
            total_signals=total,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            avg_return=avg_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_time_to_outcome=avg_time_to_outcome,
            signal_latency=timedelta(0),  # 需要额外的测量
            consistency_score=consistency_score,
            volatility=volatility,
            quality=quality,
            confidence=confidence,
            calculated_at=datetime.now()
        )

    def _get_signal_history(self, signal_name: str) -> List[Tuple[SignalRecord, SignalOutcome]]:
        """获取信号历史数据"""
        history = []

        for signal_id, record in self._signal_records.items():
            if record.signal_name == signal_name:
                outcome = self._signal_outcomes.get(signal_id)
                if outcome:
                    history.append((record, outcome))

        return history

    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """计算最大回撤"""
        if not returns:
            return 0.0

        peak = 0
        max_dd = 0
        cumulative = 0

        for r in returns:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def _determine_quality(self, accuracy: float, sharpe: float,
                          win_rate: float, consistency: float) -> SignalQuality:
        """确定信号质量等级"""
        score = (accuracy + min(1, sharpe) + win_rate + consistency) / 4

        if score >= 0.8:
            return SignalQuality.EXCELLENT
        elif score >= 0.65:
            return SignalQuality.GOOD
        elif score >= 0.5:
            return SignalQuality.FAIR
        elif score >= 0.35:
            return SignalQuality.POOR
        else:
            return SignalQuality.UNRELIABLE

    async def _update_metrics_for_signal(self, signal_id: str) -> None:
        """更新信号的指标"""
        signal = self._signal_records.get(signal_id)
        if not signal:
            return

        outcome = self._signal_outcomes.get(signal_id)
        if not outcome:
            return

        metrics = await self._calculate_full_metrics(signal, outcome)
        self._signal_metrics[signal.signal_name] = metrics

        # 保存到数据库
        if self.db:
            self._save_metrics_to_db(metrics)

        # 更新权重
        if self.config.enable_dynamic_weighting:
            self._update_signal_weight(signal.signal_name, metrics)

    def _save_metrics_to_db(self, metrics: SignalMetrics) -> None:
        """保存指标到数据库"""
        cursor = self.db.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO signal_metrics
            (signal_name, total_signals, accuracy, precision, recall, f1_score,
             avg_return, sharpe_ratio, max_drawdown, win_rate, profit_factor,
             consistency_score, quality, confidence, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metrics.signal_name,
            metrics.total_signals,
            metrics.accuracy,
            metrics.precision,
            metrics.recall,
            metrics.f1_score,
            metrics.avg_return,
            metrics.sharpe_ratio,
            metrics.max_drawdown,
            metrics.win_rate,
            metrics.profit_factor,
            metrics.consistency_score,
            metrics.quality.value,
            metrics.confidence,
            metrics.calculated_at.isoformat()
        ))
        self.db.commit()

    def _update_signal_weight(self, signal_name: str, metrics: SignalMetrics) -> None:
        """动态更新信号权重"""
        current_weight = self._signal_weights.get(signal_name, 0.2)

        # 基于质量调整权重
        quality_multiplier = {
            SignalQuality.EXCELLENT: 1.5,
            SignalQuality.GOOD: 1.2,
            SignalQuality.FAIR: 1.0,
            SignalQuality.POOR: 0.7,
            SignalQuality.UNRELIABLE: 0.3
        }

        multiplier = quality_multiplier.get(metrics.quality, 1.0)
        confidence_factor = metrics.confidence

        # 计算新权重
        target_weight = current_weight * multiplier * (0.5 + 0.5 * confidence_factor)

        # 限制调整幅度
        adjustment = (target_weight - current_weight) * self.config.weight_adjustment_factor
        new_weight = current_weight + adjustment

        # 应用边界
        new_weight = max(self.config.min_signal_weight,
                        min(self.config.max_signal_weight, new_weight))

        self._signal_weights[signal_name] = new_weight

        logger.debug(f"Signal {signal_name} weight updated: {current_weight:.3f} -> {new_weight:.3f}")

    def get_signal_weight(self, signal_name: str) -> float:
        """获取信号权重"""
        return self._signal_weights.get(signal_name, 0.2)

    def get_all_weights(self) -> Dict[str, float]:
        """获取所有信号权重"""
        return self._signal_weights.copy()

    def normalize_weights(self) -> Dict[str, float]:
        """归一化权重"""
        if not self._signal_weights:
            return {}

        total = sum(self._signal_weights.values())
        if total == 0:
            # 均匀分配
            n = len(self._signal_weights)
            return {k: 1.0 / n for k in self._signal_weights}

        return {k: v / total for k, v in self._signal_weights.items()}

    def get_signal_metrics(self, signal_name: str) -> Optional[SignalMetrics]:
        """获取信号指标"""
        return self._signal_metrics.get(signal_name)

    def get_all_metrics(self) -> Dict[str, SignalMetrics]:
        """获取所有信号指标"""
        return self._signal_metrics.copy()

    def get_top_signals(self, n: int = 5,
                       criterion: str = "sharpe_ratio") -> List[Tuple[str, SignalMetrics]]:
        """
        获取表现最佳的信号

        Args:
            n: 返回数量
            criterion: 排序标准（accuracy, sharpe_ratio, win_rate, profit_factor等）
        """
        valid_metrics = []
        for name, metrics in self._signal_metrics.items():
            if metrics.total_signals >= self.config.min_samples_for_metrics:
                valid_metrics.append((name, metrics))

        if not valid_metrics:
            return []

        # 排序
        reverse = True  # 默认降序
        if criterion in ['max_drawdown', 'volatility']:
            reverse = False  # 这些指标越低越好

        try:
            sorted_metrics = sorted(
                valid_metrics,
                key=lambda x: getattr(x[1], criterion, 0),
                reverse=reverse
            )
        except AttributeError:
            logger.warning(f"Invalid criterion: {criterion}")
            sorted_metrics = valid_metrics

        return sorted_metrics[:n]

    def get_signal_recommendations(self) -> Dict[str, Any]:
        """获取信号优化建议"""
        recommendations = {
            'add_signals': [],
            'remove_signals': [],
            'adjust_weights': {},
            'improve_timing': []
        }

        for name, metrics in self._signal_metrics.items():
            # 建议移除低质量信号
            if metrics.quality == SignalQuality.UNRELIABLE:
                if metrics.total_signals >= self.config.min_samples_for_metrics:
                    recommendations['remove_signals'].append({
                        'signal': name,
                        'reason': f"Unreliable quality with {metrics.accuracy:.2%} accuracy"
                    })

            # 建议调整权重
            current_weight = self._signal_weights.get(name, 0.2)
            target_weight = self._calculate_target_weight(metrics)

            if abs(target_weight - current_weight) > 0.05:
                recommendations['adjust_weights'][name] = {
                    'current': current_weight,
                    'target': target_weight,
                    'reason': f"Quality: {metrics.quality.value}, Sharpe: {metrics.sharpe_ratio:.2f}"
                }

            # 建议改进时效性
            if metrics.avg_time_to_outcome > timedelta(hours=24):
                recommendations['improve_timing'].append({
                    'signal': name,
                    'current_latency': str(metrics.avg_time_to_outcome),
                    'suggestion': 'Consider earlier entry or shorter timeframe'
                })

        # 建议添加互补信号
        if len(self._signal_metrics) < 5:
            recommendations['add_signals'].append({
                'suggestion': 'Consider adding momentum-based signals for diversification',
                'rationale': f"Current signal count ({len(self._signal_metrics)}) is low for robust ensemble"
            })

        return recommendations

    def _calculate_target_weight(self, metrics: SignalMetrics) -> float:
        """计算目标权重"""
        base_weight = 0.2

        # 基于质量调整
        quality_multiplier = {
            SignalQuality.EXCELLENT: 2.0,
            SignalQuality.GOOD: 1.5,
            SignalQuality.FAIR: 1.0,
            SignalQuality.POOR: 0.5,
            SignalQuality.UNRELIABLE: 0.1
        }

        multiplier = quality_multiplier.get(metrics.quality, 1.0)

        # 基于夏普比率微调
        sharpe_adjustment = min(0.5, max(-0.3, metrics.sharpe_ratio * 0.1))

        target = base_weight * multiplier + sharpe_adjustment

        # 应用边界
        return max(self.config.min_signal_weight,
                   min(self.config.max_signal_weight, target))

    def export_data(self, filepath: str) -> None:
        """导出评估数据到JSON文件"""
        data = {
            'metrics': {name: metrics.to_dict() for name, metrics in self._signal_metrics.items()},
            'weights': self._signal_weights,
            'normalized_weights': self.normalize_weights(),
            'stats': self._stats,
            'exported_at': datetime.now().isoformat()
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Signal data exported to {filepath}")

    def get_stats(self) -> Dict[str, Any]:
        """获取评估统计"""
        return self._stats.copy()


# 辅助函数
def create_default_signal_evaluator(db_path: Optional[str] = None) -> SignalEvaluator:
    """创建默认的信号评估器"""
    db = None
    if db_path:
        db = sqlite3.connect(db_path, check_same_thread=False)

    return SignalEvaluator(db)


def evaluate_signals_batch(evaluator: SignalEvaluator,
                          signals: List[SignalRecord]) -> Dict[str, SignalMetrics]:
    """批量评估信号"""
    results = {}

    for signal in signals:
        # 异步运行评估
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        metrics = loop.run_until_complete(evaluator.evaluate_signal(signal.signal_id))
        if metrics:
            results[signal.signal_name] = metrics

    return results
