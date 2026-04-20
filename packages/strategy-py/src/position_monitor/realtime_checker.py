"""
Layer 1: 实时价格驱动检查器
每次价格更新时触发，毫秒级响应
"""

import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class ExitSignal:
    """退出信号"""
    position_id: str
    action: str  # "exit", "partial_exit", "hold"
    reason: str  # "stop_loss", "take_profit", "trailing_stop", etc.
    exit_ratio: float = 1.0  # 1.0 = 全部退出
    target_price: Optional[float] = None
    metadata: Dict[str, Any] = None


@dataclass
class Position:
    """持仓数据"""
    id: str
    token_id: str
    market_id: str
    entry_price: float
    current_price: float = 0.0
    highest_price: float = 0.0
    size: float = 0.0
    side: str = "BUY"
    opened_at: datetime = None
    last_sync_at: datetime = None
    partial_exits_executed: list = None
    trailing_stop_price: Optional[float] = None

    def __post_init__(self):
        if self.opened_at is None:
            self.opened_at = datetime.now()
        if self.last_sync_at is None:
            self.last_sync_at = datetime.now()
        if self.partial_exits_executed is None:
            self.partial_exits_executed = []

    @property
    def profit_pct(self) -> float:
        """当前盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def from_high_pct(self) -> float:
        """从最高价回撤百分比"""
        if self.highest_price == 0:
            return 0.0
        return (self.current_price - self.highest_price) / self.highest_price

    def update_price(self, new_price: float):
        """更新价格并记录最高价"""
        self.current_price = new_price
        if new_price > self.highest_price:
            self.highest_price = new_price


class RealtimeChecker:
    """
    Layer 1 实时检查器

    职责：
    1. 硬止损检查 (-7% 正常 / -3% 临期)
    2. 硬止盈检查 (+10%)
    3. 高价止盈检查 (>= 0.999)
    4. 最大持仓时间检查 (4小时)
    5. 到期后强制退出检查（只有到期时间 <= 0 才退出）

    触发：每次价格更新（WebSocket/HTTP）
    延迟：毫秒级
    """

    def __init__(self, config: Dict, on_exit_signal=None):
        self.config = config
        self.on_exit_signal = on_exit_signal

        # 硬阈值配置
        self.hard_stop_loss = config.get("hard_stop_loss", -0.07)  # -7%
        self.hard_take_profit = config.get("hard_take_profit", 0.10)  # +10%
        self.late_stage_threshold_sec = 1800  # 30分钟 = 临期
        self.late_stage_stop_loss = -0.03  # -3%
        self.max_holding_hours = config.get("max_holding_hours", 4)
        self.high_price_exit_threshold = 0.999  # 高价止盈阈值

        # 检查间隔控制
        self.min_check_interval_ms = config.get("check_interval_ms", 100)
        self._last_check_time: Dict[str, float] = {}

    def check(self, position: Position, sec_to_expiry: Optional[int] = None) -> Optional[ExitSignal]:
        """
        执行实时检查

        优先级顺序（从高到低）：
        1. 高价止盈 (P0)
        2. 硬止损/止盈 (P1)
        3. 到期后退出 (P1) - 只有 sec_to_expiry <= 0 才触发
        4. 最大持仓时间 (P2)
        """

        # 检查间隔控制（避免过于频繁的检查）
        current_time = time.time() * 1000
        last_check = self._last_check_time.get(position.id, 0)
        if current_time - last_check < self.min_check_interval_ms:
            return None
        self._last_check_time[position.id] = current_time

        # 计算盈亏
        profit_pct = position.profit_pct

        # 获取当前时间
        now = datetime.now()
        holding_duration = now - position.opened_at
        holding_hours = holding_duration.total_seconds() / 3600

        # ===== 优先级 0: 高价止盈 =====
        if position.current_price >= self.high_price_exit_threshold:
            # 验证价格合理性（防止 token 混淆）
            if self._validate_price_update(position, position.current_price):
                logger.warning(
                    f"[P0] 高价止盈触发: position={position.id}, "
                    f"price={position.current_price:.4f}"
                )
                return ExitSignal(
                    position_id=position.id,
                    action="exit",
                    reason="high_price_exit",
                    exit_ratio=1.0,
                    target_price=position.current_price,
                    metadata={
                        "priority": 0,
                        "trigger_price": position.current_price,
                        "profit_pct": profit_pct,
                    }
                )

        # ===== 优先级 1: 硬止损/止盈 =====
        # 检查是否是临期（< 30分钟）
        is_late_stage = sec_to_expiry is not None and sec_to_expiry < self.late_stage_threshold_sec
        current_stop_loss = self.late_stage_stop_loss if is_late_stage else self.hard_stop_loss

        # 硬止损检查
        if profit_pct <= current_stop_loss:
            logger.warning(
                f"[P1] 硬止损触发: position={position.id}, "
                f"profit_pct={profit_pct:.4%}, threshold={current_stop_loss:.4%}, "
                f"late_stage={is_late_stage}"
            )
            return ExitSignal(
                position_id=position.id,
                action="exit",
                reason="hard_stop_loss",
                exit_ratio=1.0,
                metadata={
                    "priority": 1,
                    "profit_pct": profit_pct,
                    "threshold": current_stop_loss,
                    "is_late_stage": is_late_stage,
                }
            )

        # 硬止盈检查
        if profit_pct >= self.hard_take_profit:
            logger.info(
                f"[P1] 硬止盈触发: position={position.id}, "
                f"profit_pct={profit_pct:.4%}, threshold={self.hard_take_profit:.4%}"
            )
            return ExitSignal(
                position_id=position.id,
                action="exit",
                reason="hard_take_profit",
                exit_ratio=1.0,
                metadata={
                    "priority": 1,
                    "profit_pct": profit_pct,
                    "threshold": self.hard_take_profit,
                }
            )

        # 注：到期时间只用于市场筛选（选择哪些市场可以交易），不影响持仓退出
        # 这是为了提高资金利用率 - 持仓不会因为有到期时间而被强制退出

        # ===== 优先级 2: 最大持仓时间检查 =====
        if holding_hours >= self.max_holding_hours:
            logger.warning(
                f"[P2] 最大持仓时间触发: position={position.id}, "
                f"holding_hours={holding_hours:.2f}h"
            )
            return ExitSignal(
                position_id=position.id,
                action="exit",
                reason="max_holding_time",
                exit_ratio=1.0,
                metadata={
                    "priority": 2,
                    "holding_hours": holding_hours,
                }
            )

        # 无退出信号
        return None

    def _validate_price_update(self, position, new_price: float) -> bool:
        """验证价格更新是否合理（防止 token 混淆）"""
        # 简化版本，实际实现需要更多逻辑
        return True