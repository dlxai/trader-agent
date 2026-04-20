"""
固定止损服务 (Fixed Stop Loss Service)
基于价格区间的动态固定止损阈值配置
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from ..config.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class StopLossLevel:
    """止损档位配置"""
    min_price: float
    max_price: float
    threshold: float  # 负数，如 -0.07 表示 -7%
    description: str


@dataclass
class StopLossSignal:
    """止损信号"""
    position_id: str
    trigger_type: str  # "fixed_stop_loss"
    entry_price: float
    current_price: float
    threshold: float  # 止损阈值（如 -0.07）
    profit_pct: float  # 当前盈亏百分比
    should_exit: bool = True
    exit_ratio: float = 1.0  # 固定止损全部退出
    reason: str = "Fixed stop loss triggered"


class FixedStopLossService:
    """
    固定止损服务

    基于价格区间的动态止损阈值配置
    根据入场价确定对应的止损阈值

    配置（来自 settings.stop_loss.fixed_thresholds）:
    - $0.00-$0.20: -30%
    - $0.20-$0.40: -25%
    - $0.40-$0.60: -20%
    - $0.60-$0.75: -15%
    - $0.75-$0.85: -12%
    - $0.85-$0.90: -10%
    - $0.90-$0.95: -5%
    - $0.95-$0.97: -4%
    - $0.97-$0.99: -3%
    - $0.99-$1.00: -2%
    """

    def __init__(self, thresholds: Optional[List[Dict]] = None):
        """
        初始化固定止损服务

        Args:
            thresholds: 自定义阈值配置，默认使用 settings.stop_loss.fixed_thresholds
        """
        self.enabled = settings.stop_loss.fixed_stop_enabled if hasattr(settings.stop_loss, 'fixed_stop_enabled') else True

        # 初始化阈值配置
        if thresholds:
            self.levels = self._parse_config(thresholds)
        else:
            self.levels = self._default_config()

        # 统计信息
        self._trigger_count: int = 0
        self._check_count: int = 0

        logger.info(
            f"Fixed stop loss service initialized with {len(self.levels)} levels: "
            f"{[f'${l.min_price:.2f}-${l.max_price:.2f}:{l.threshold:.0%}' for l in self.levels]}"
        )

    def _default_config(self) -> List[StopLossLevel]:
        """默认阈值配置（从 settings 加载）"""
        thresholds = settings.stop_loss.fixed_thresholds
        levels = []

        for t in thresholds:
            min_price = t.get("min", 0.0)
            max_price = t.get("max", 1.0)
            threshold = t.get("threshold", -0.30)

            # 生成描述
            description = self._generate_description(min_price, max_price, threshold)

            levels.append(StopLossLevel(
                min_price=min_price,
                max_price=max_price,
                threshold=threshold,
                description=description
            ))

        return levels

    def _generate_description(self, min_price: float, max_price: float, threshold: float) -> str:
        """生成档位描述"""
        price_range = f"${min_price:.2f}-${max_price:.2f}"

        # 根据价格区间和阈值生成描述
        if min_price < 0.20:
            return f"极低价区 {price_range}: 强保护，止损阈值 {threshold:.0%}"
        elif min_price < 0.40:
            return f"低价区 {price_range}: 较高波动，止损阈值 {threshold:.0%}"
        elif min_price < 0.60:
            return f"中低价区 {price_range}: 中等波动，止损阈值 {threshold:.0%}"
        elif min_price < 0.75:
            return f"中价区 {price_range}: 标准止损，止损阈值 {threshold:.0%}"
        elif min_price < 0.85:
            return f"中高价区 {price_range}: 较紧止损，止损阈值 {threshold:.0%}"
        elif min_price < 0.90:
            return f"高价区 {price_range}: 严格止损，止损阈值 {threshold:.0%}"
        elif min_price < 0.95:
            return f"准扫尾盘区 {price_range}: 极紧止损，止损阈值 {threshold:.0%}"
        elif min_price < 0.97:
            return f"扫尾盘低档区 {price_range}: 超紧止损，止损阈值 {threshold:.0%}"
        elif min_price < 0.99:
            return f"扫尾盘中档区 {price_range}: 极微止损，止损阈值 {threshold:.0%}"
        else:
            return f"扫尾盘高档区 {price_range}: 最微止损，止损阈值 {threshold:.0%}"

    def _parse_config(self, config: List[Dict]) -> List[StopLossLevel]:
        """解析自定义配置"""
        levels = []
        for item in config:
            level = StopLossLevel(
                min_price=item.get("min", 0.0),
                max_price=item.get("max", 1.0),
                threshold=item.get("threshold", -0.30),
                description=item.get("description", ""),
            )
            levels.append(level)
        return sorted(levels, key=lambda x: x.min_price)

    def get_stop_loss_threshold(self, entry_price: float) -> float:
        """
        根据入场价获取对应的止损阈值

        Args:
            entry_price: 入场价格

        Returns:
            float: 止损阈值（负数，如 -0.07 表示 -7%）
        """
        level = self.get_stop_loss_level(entry_price)
        if level:
            return level.threshold

        # 默认返回 -30%（最保守）
        logger.warning(f"No stop loss level found for entry price {entry_price}, using default -30%")
        return -0.30

    def get_stop_loss_level(self, entry_price: float) -> Optional[StopLossLevel]:
        """
        获取对应的止损档位

        Args:
            entry_price: 入场价格

        Returns:
            StopLossLevel 如果找到对应档位，否则 None
        """
        if entry_price < 0 or entry_price > 1.0:
            logger.error(f"Invalid entry price: {entry_price}, must be in [0, 1]")
            return None

        for level in self.levels:
            if level.min_price <= entry_price < level.max_price:
                return level

        # 处理边界情况（entry_price = 1.0）
        if entry_price == 1.0:
            return self.levels[-1] if self.levels else None

        return None

    def calculate_profit_pct(self, entry_price: float, current_price: float) -> float:
        """
        计算盈亏百分比

        Args:
            entry_price: 入场价格
            current_price: 当前价格

        Returns:
            float: 盈亏百分比（如 0.05 表示 +5%，-0.03 表示 -3%）
        """
        if entry_price <= 0:
            logger.error(f"Invalid entry price: {entry_price}")
            return 0.0

        return (current_price - entry_price) / entry_price

    def check_stop_loss(
        self,
        position_id: str,
        entry_price: float,
        current_price: float
    ) -> Optional[StopLossSignal]:
        """
        检查是否触发固定止损

        Args:
            position_id: 持仓ID
            entry_price: 入场价
            current_price: 当前价

        Returns:
            StopLossSignal 如果触发止损，否则 None
        """
        self._check_count += 1

        if not self.enabled:
            return None

        # 验证价格有效性
        if entry_price <= 0 or current_price <= 0:
            logger.error(f"Invalid prices: entry={entry_price}, current={current_price}")
            return None

        # 获取止损阈值
        threshold = self.get_stop_loss_threshold(entry_price)

        # 计算当前盈亏百分比
        profit_pct = self.calculate_profit_pct(entry_price, current_price)

        # 检查是否触发止损（亏损超过阈值）
        if profit_pct <= threshold:
            self._trigger_count += 1

            logger.warning(
                f"Fixed stop loss TRIGGERED for {position_id}: "
                f"entry={entry_price:.4f}, current={current_price:.4f}, "
                f"profit={profit_pct:.2%}, threshold={threshold:.2%}"
            )

            return StopLossSignal(
                position_id=position_id,
                trigger_type="fixed_stop_loss",
                entry_price=entry_price,
                current_price=current_price,
                threshold=threshold,
                profit_pct=profit_pct,
                should_exit=True,
                exit_ratio=1.0,  # 固定止损全部退出
                reason=f"Fixed stop loss triggered: profit {profit_pct:.2%} <= threshold {threshold:.2%}"
            )

        return None

    def validate_thresholds(self) -> bool:
        """
        验证阈值配置是否有效

        Returns:
            bool: 配置是否有效
        """
        if not self.levels:
            logger.error("No stop loss levels configured")
            return False

        # 检查档位是否连续覆盖 [0, 1] 区间
        expected_min = 0.0

        for i, level in enumerate(self.levels):
            # 检查阈值是否为负数
            if level.threshold >= 0:
                logger.error(f"Level {i}: threshold must be negative, got {level.threshold}")
                return False

            # 检查区间是否连续
            if abs(level.min_price - expected_min) > 0.001:
                logger.error(f"Level {i}: expected min_price {expected_min}, got {level.min_price}")
                return False

            expected_min = level.max_price

        # 检查最后一个档位是否覆盖到 1.0
        if abs(expected_min - 1.0) > 0.001:
            logger.error(f"Last level should cover up to 1.0, got {expected_min}")
            return False

        logger.info(f"Thresholds validation passed: {len(self.levels)} levels covering [0, 1]")
        return True

    def get_stats(self) -> Dict:
        """
        获取服务统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "enabled": self.enabled,
            "total_levels": len(self.levels),
            "check_count": self._check_count,
            "trigger_count": self._trigger_count,
            "trigger_rate": self._trigger_count / self._check_count if self._check_count > 0 else 0,
            "levels_config": [
                {
                    "min_price": l.min_price,
                    "max_price": l.max_price,
                    "threshold": l.threshold,
                    "description": l.description,
                }
                for l in self.levels
            ],
        }
