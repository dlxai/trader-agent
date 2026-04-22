"""
分层止盈服务 (Partial Exit Service)
在利润达到不同目标时分批卖出，锁定利润
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from config.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class PartialExitLevel:
    """分层止盈档位"""
    level: int
    profit_level: float  # 利润目标（如 0.20 = 20%）
    exit_ratio: float  # 卖出比例（如 0.30 = 30%）
    description: str


@dataclass
class PartialExitSignal:
    """分层止盈信号"""
    position_id: str
    level: int
    exit_ratio: float
    current_profit: float
    target_profit: float
    should_execute: bool


class PartialExitService:
    """
    分层止盈服务

    实现 3 档分层止盈：
    - Level 1: 20% 利润，卖出 30%
    - Level 2: 40% 利润，卖出 30%
    - Level 3: 60% 利润，卖出 40%

    优势：
    1. 锁定利润：在不同利润点分批卖出，防止利润回吐
    2. 保留上涨空间：不会一次性全部卖出，保留后续涨幅
    3. 灵活应对：根据市场情况选择是否执行每档止盈
    """

    def __init__(self, custom_config: Optional[List[Dict]] = None):
        """
        初始化分层止盈服务

        Args:
            custom_config: 自定义分层配置，如果为 None 则使用默认配置
        """
        self.enabled = settings.stop_loss.partial_exit_enabled

        # 初始化分层配置
        if custom_config:
            self.levels = self._parse_config(custom_config)
        else:
            self.levels = self._default_config()

        # 记录已执行的档位
        self._executed_levels: Dict[str, List[int]] = {}

        logger.info(
            f"Partial exit service initialized with {len(self.levels)} levels: "
            f"{[f'L{l.level}:{l.profit_level:.0%}' for l in self.levels]}"
        )

    def _default_config(self) -> List[PartialExitLevel]:
        """默认分层配置"""
        return [
            PartialExitLevel(
                level=1,
                profit_level=0.20,
                exit_ratio=0.30,
                description="+20% profit, sell 30%",
            ),
            PartialExitLevel(
                level=2,
                profit_level=0.40,
                exit_ratio=0.30,
                description="+40% profit, sell 30%",
            ),
            PartialExitLevel(
                level=3,
                profit_level=0.60,
                exit_ratio=0.40,
                description="+60% profit, sell remaining 40%",
            ),
        ]

    def _parse_config(self, config: List[Dict]) -> List[PartialExitLevel]:
        """解析自定义配置"""
        levels = []
        for item in config:
            level = PartialExitLevel(
                level=item["level"],
                profit_level=item["profit_level"],
                exit_ratio=item["exit_ratio"],
                description=item.get("description", ""),
            )
            levels.append(level)
        return sorted(levels, key=lambda x: x.level)

    def check(self, position_id: str, current_profit: float) -> Optional[PartialExitSignal]:
        """
        检查是否触发分层止盈

        Args:
            position_id: 持仓 ID
            current_profit: 当前利润（如 0.25 = 25%）

        Returns:
            PartialExitSignal 如果触发止盈，否则 None
        """
        if not self.enabled:
            return None

        # 获取已执行的档位
        executed = self._executed_levels.get(position_id, [])

        # 检查每个档位
        for level in self.levels:
            # 跳过已执行的档位
            if level.level in executed:
                continue

            # 检查是否达到利润目标
            if current_profit >= level.profit_level:
                logger.info(
                    f"Partial exit Level {level.level} triggered for {position_id}: "
                    f"profit={current_profit:.2%}, target={level.profit_level:.2%}, "
                    f"exit_ratio={level.exit_ratio:.0%}"
                )

                return PartialExitSignal(
                    position_id=position_id,
                    level=level.level,
                    exit_ratio=level.exit_ratio,
                    current_profit=current_profit,
                    target_profit=level.profit_level,
                    should_execute=True,
                )

        # 未达到任何档位
        return None

    def mark_level_executed(self, position_id: str, level: int):
        """
        标记某个档位已执行

        Args:
            position_id: 持仓 ID
            level: 档位编号（1, 2, 3）
        """
        if position_id not in self._executed_levels:
            self._executed_levels[position_id] = []

        if level not in self._executed_levels[position_id]:
            self._executed_levels[position_id].append(level)
            logger.debug(f"Marked level {level} as executed for {position_id}")

    def reset_position(self, position_id: str):
        """重置持仓的执行记录（用于测试或重新开仓）"""
        if position_id in self._executed_levels:
            del self._executed_levels[position_id]
            logger.debug(f"Reset partial exit tracking for {position_id}")

    def get_position_status(self, position_id: str) -> Dict:
        """获取持仓的分层止盈状态"""
        executed = self._executed_levels.get(position_id, [])

        return {
            "position_id": position_id,
            "enabled": self.enabled,
            "total_levels": len(self.levels),
            "executed_levels": executed,
            "remaining_levels": [l.level for l in self.levels if l.level not in executed],
            "next_level": self._get_next_level(executed),
        }

    def _get_next_level(self, executed: List[int]) -> Optional[Dict]:
        """获取下一个要触发的档位"""
        for level in self.levels:
            if level.level not in executed:
                return {
                    "level": level.level,
                    "profit_target": level.profit_level,
                    "exit_ratio": level.exit_ratio,
                    "description": level.description,
                }
        return None

    def get_all_levels(self) -> List[Dict]:
        """获取所有档位配置"""
        return [
            {
                "level": level.level,
                "profit_target": level.profit_level,
                "exit_ratio": level.exit_ratio,
                "description": level.description,
            }
            for level in self.levels
        ]
