"""
移动止损服务 (Trailing Stop Service)
随着价格上涨动态调整止损位，保护已获得的利润
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from ..config.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class TrailingStopLevel:
    """移动止损档位"""
    min_entry: float  # 入场价区间下限
    max_entry: float  # 入场价区间上限
    trigger_profit: float  # 触发利润（如 0.30 = 30%）
    drawdown: float  # 允许回撤幅度（如 0.15 = 15%）
    description: str


@dataclass
class TrailingStopState:
    """移动止损状态"""
    position_id: str
    highest_price: float  # 最高价
    trailing_stop_price: float  # 当前移动止损价
    trigger_profit: float  # 触发利润
    drawdown: float  # 回撤幅度
    is_active: bool  # 是否已激活
    activated_at: Optional[datetime] = None


class TrailingStopService:
    """
    移动止损服务

    实现 6 档移动止损，根据入场价格区间和已锁定利润动态调整：

    入场价 $0.00-$0.30: 利润 +30% 触发，回撤 15%
    入场价 $0.30-$0.60: 利润 +40% 触发，回撤 12%
    入场价 $0.60-$0.75: 利润 +30% 触发，回撤 10%
    入场价 $0.75-$0.85: 利润 +24% 触发，回撤 8%
    入场价 $0.85-$0.90: 利润 +20% 触发，回撤 6%
    入场价 $0.90-$1.00: 利润 +15% 触发，回撤 5%

    核心逻辑：
    1. 跟踪最高价
    2. 达到触发利润时激活移动止损
    3. 从最高价回撤超过阈值时触发退出
    """

    def __init__(self, custom_config: Optional[List[Dict]] = None):
        """
        初始化移动止损服务

        Args:
            custom_config: 自定义移动止损配置
        """
        self.enabled = settings.stop_loss.trailing_stop_enabled

        # 初始化档位配置
        if custom_config:
            self.levels = self._parse_config(custom_config)
        else:
            self.levels = self._default_config()

        # 追踪每个持仓的移动止损状态
        self._states: Dict[str, TrailingStopState] = {}

        logger.info(
            f"Trailing stop service initialized with {len(self.levels)} levels"
        )

    def _default_config(self) -> List[TrailingStopLevel]:
        """默认移动止损配置（6档）"""
        return [
            TrailingStopLevel(
                min_entry=0.00,
                max_entry=0.30,
                trigger_profit=0.30,
                drawdown=0.15,
                description="Entry $0.00-0.30: 30% profit trigger, 15% drawdown",
            ),
            TrailingStopLevel(
                min_entry=0.30,
                max_entry=0.60,
                trigger_profit=0.40,
                drawdown=0.12,
                description="Entry $0.30-0.60: 40% profit trigger, 12% drawdown",
            ),
            TrailingStopLevel(
                min_entry=0.60,
                max_entry=0.75,
                trigger_profit=0.30,
                drawdown=0.10,
                description="Entry $0.60-0.75: 30% profit trigger, 10% drawdown",
            ),
            TrailingStopLevel(
                min_entry=0.75,
                max_entry=0.85,
                trigger_profit=0.24,
                drawdown=0.08,
                description="Entry $0.75-0.85: 24% profit trigger, 8% drawdown",
            ),
            TrailingStopLevel(
                min_entry=0.85,
                max_entry=0.90,
                trigger_profit=0.20,
                drawdown=0.06,
                description="Entry $0.85-0.90: 20% profit trigger, 6% drawdown",
            ),
            TrailingStopLevel(
                min_entry=0.90,
                max_entry=1.00,
                trigger_profit=0.15,
                drawdown=0.05,
                description="Entry $0.90-1.00: 15% profit trigger, 5% drawdown",
            ),
        ]

    def _parse_config(self, config: List[Dict]) -> List[TrailingStopLevel]:
        """解析自定义配置"""
        levels = []
        for item in config:
            level = TrailingStopLevel(
                min_entry=item["min_entry"],
                max_entry=item["max_entry"],
                trigger_profit=item["trigger_profit"],
                drawdown=item["drawdown"],
                description=item.get("description", ""),
            )
            levels.append(level)
        return sorted(levels, key=lambda x: x.min_entry)

    def initialize_position(
        self, position_id: str, entry_price: float, initial_price: float
    ) -> TrailingStopState:
        """
        初始化持仓的移动止损状态

        Args:
            position_id: 持仓 ID
            entry_price: 入场价格
            initial_price: 初始当前价格

        Returns:
            TrailingStopState: 初始化的状态
        """
        # 根据入场价格确定档位
        level = self._get_level_for_entry(entry_price)

        # 初始止损价设为入场价（或稍微下方）
        initial_stop = entry_price * 0.95  # 默认 5% 止损

        state = TrailingStopState(
            position_id=position_id,
            highest_price=initial_price,
            trailing_stop_price=initial_stop,
            trigger_profit=level.trigger_profit if level else 0.30,
            drawdown=level.drawdown if level else 0.15,
            is_active=False,
            activated_at=None,
        )

        self._states[position_id] = state

        logger.debug(
            f"Initialized trailing stop for {position_id}: "
            f"entry={entry_price:.4f}, stop={initial_stop:.4f}, "
            f"trigger={state.trigger_profit:.0%}, drawdown={state.drawdown:.0%}"
        )

        return state

    def _get_level_for_entry(self, entry_price: float) -> Optional[TrailingStopLevel]:
        """根据入场价格获取对应档位"""
        for level in self.levels:
            if level.min_entry <= entry_price < level.max_entry:
                return level
        return None

    def update_price(self, position_id: str, current_price: float) -> Optional[Dict]:
        """
        更新价格并检查移动止损

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            Dict 如果触发移动止损，包含退出信号信息
            None 如果没有触发
        """
        if not self.enabled:
            return None

        state = self._states.get(position_id)
        if not state:
            logger.warning(f"No trailing stop state for position {position_id}")
            return None

        # 更新最高价
        if current_price > state.highest_price:
            state.highest_price = current_price

        # 计算当前利润
        if state.trailing_stop_price <= 0:
            return None

        profit_pct = (current_price - state.trailing_stop_price) / state.trailing_stop_price

        # 检查是否激活移动止损
        if not state.is_active:
            if profit_pct >= state.trigger_profit:
                # 激活移动止损
                state.is_active = True
                state.activated_at = datetime.now()

                # 设置初始移动止损价（从最高价回撤指定幅度）
                state.trailing_stop_price = state.highest_price * (1 - state.drawdown)

                logger.info(
                    f"Trailing stop ACTIVATED for {position_id}: "
                    f"highest={state.highest_price:.4f}, "
                    f"stop_price={state.trailing_stop_price:.4f}, "
                    f"drawdown={state.drawdown:.0%}"
                )

        # 检查是否触发移动止损
        if state.is_active:
            # 更新移动止损价（如果价格创新高）
            new_stop = state.highest_price * (1 - state.drawdown)
            if new_stop > state.trailing_stop_price:
                state.trailing_stop_price = new_stop
                logger.debug(
                    f"Trailing stop UPDATED for {position_id}: "
                    f"new_stop={state.trailing_stop_price:.4f}"
                )

            # 检查是否触发
            if current_price <= state.trailing_stop_price:
                logger.warning(
                    f"Trailing stop TRIGGERED for {position_id}: "
                    f"current={current_price:.4f}, "
                    f"stop={state.trailing_stop_price:.4f}, "
                    f"highest={state.highest_price:.4f}"
                )

                return {
                    "position_id": position_id,
                    "action": "exit",
                    "reason": "trailing_stop",
                    "exit_ratio": 1.0,
                    "current_price": current_price,
                    "trailing_stop_price": state.trailing_stop_price,
                    "highest_price": state.highest_price,
                    "drawdown": state.drawdown,
                    "activated_at": state.activated_at.isoformat() if state.activated_at else None,
                }

        return None

    def get_state(self, position_id: str) -> Optional[Dict]:
        """获取持仓的移动止损状态"""
        state = self._states.get(position_id)
        if not state:
            return None

        return {
            "position_id": state.position_id,
            "highest_price": state.highest_price,
            "trailing_stop_price": state.trailing_stop_price,
            "trigger_profit": state.trigger_profit,
            "drawdown": state.drawdown,
            "is_active": state.is_active,
            "activated_at": state.activated_at.isoformat() if state.activated_at else None,
        }

    def reset_position(self, position_id: str):
        """重置持仓的移动止损状态"""
        if position_id in self._states:
            del self._states[position_id]
            logger.debug(f"Reset trailing stop state for {position_id}")

    def get_all_states(self) -> Dict[str, Dict]:
        """获取所有持仓的移动止损状态"""
        return {pid: self.get_state(pid) for pid in self._states.keys()}

    def get_stats(self) -> Dict:
        """获取服务统计信息"""
        active_count = sum(1 for s in self._states.values() if s.is_active)

        return {
            "enabled": self.enabled,
            "total_levels": len(self.levels),
            "tracked_positions": len(self._states),
            "active_positions": active_count,
            "levels_config": [
                {
                    "min_entry": l.min_entry,
                    "max_entry": l.max_entry,
                    "trigger_profit": l.trigger_profit,
                    "drawdown": l.drawdown,
                }
                for l in self.levels
            ],
        }
