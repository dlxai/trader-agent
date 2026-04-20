"""
价格保护模块 (Price Protection)
包含高价止盈检测和 Token 混淆检测
"""

import logging
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger(__name__)


@dataclass
class HighPriceExitSignal:
    """高价止盈信号"""
    position_id: str
    current_price: float
    threshold: float
    should_exit: bool
    reason: str


@dataclass
class TokenConfusionAlert:
    """Token 混淆警报"""
    position_id: str
    token_id: str
    detected_price: float
    expected_price_range: tuple
    confidence: float
    reason: str
    recommended_action: str


class PriceProtection:
    """
    价格保护服务

    提供两个核心功能：
    1. 高价止盈检测：当价格 >= 0.999 时触发紧急退出
    2. Token 混淆检测：检测异常价格变动，防止买入错误的 token
    """

    def __init__(
        self,
        high_price_threshold: float = 0.999,
        enable_confusion_detection: bool = True,
        on_confusion_alert: Optional[Callable[[TokenConfusionAlert], None]] = None,
    ):
        """
        初始化价格保护服务

        Args:
            high_price_threshold: 高价止盈阈值（默认 0.999）
            enable_confusion_detection: 是否启用混淆检测
            on_confusion_alert: 混淆警报回调函数
        """
        self.high_price_threshold = high_price_threshold
        self.enable_confusion_detection = enable_confusion_detection
        self.on_confusion_alert = on_confusion_alert

        # 统计
        self._high_price_exits = 0
        self._confusion_alerts = 0
        self._blocked_trades = 0

        logger.info(
            f"Price protection initialized: high_price_threshold={high_price_threshold}, "
            f"confusion_detection={enable_confusion_detection}"
        )

    def check_high_price_exit(
        self, position_id: str, current_price: float
    ) -> Optional[HighPriceExitSignal]:
        """
        检查是否触发高价止盈

        Args:
            position_id: 持仓 ID
            current_price: 当前价格

        Returns:
            HighPriceExitSignal 如果触发，否则 None
        """
        if current_price >= self.high_price_threshold:
            self._high_price_exits += 1

            logger.warning(
                f"HIGH PRICE EXIT triggered for {position_id}: "
                f"current_price={current_price:.4f}, "
                f"threshold={self.high_price_threshold:.4f}"
            )

            return HighPriceExitSignal(
                position_id=position_id,
                current_price=current_price,
                threshold=self.high_price_threshold,
                should_exit=True,
                reason=f"Price reached extreme level ({current_price:.4f} >= {self.high_price_threshold:.4f})",
            )

        return None


class TokenConfusionDetector:
    """
    Token 混淆检测器

    检测异常价格变动，防止由于 token 混淆（如买入 YES token 但跟踪了 NO token 的价格）
    导致的错误交易。

    检测条件：
    1. 价格变化 > 20% 且接近极端值
    2. 价格与入场价互补（和接近 1.0）
    3. 反向价格变化更小
    """

    def __init__(
        self,
        price_change_threshold: float = 0.20,
        complementary_threshold: float = 0.05,
        on_confusion_detected: Optional[Callable[[TokenConfusionAlert], None]] = None,
    ):
        """
        初始化 Token 混淆检测器

        Args:
            price_change_threshold: 价格变化阈值（默认 20%）
            complementary_threshold: 互补检测阈值（默认 0.05）
            on_confusion_detected: 混淆检测回调
        """
        self.price_change_threshold = price_change_threshold
        self.complementary_threshold = complementary_threshold
        self.on_confusion_detected = on_confusion_detected

        # 统计
        self._detections = 0
        self._false_positives = 0

        logger.info(
            f"Token confusion detector initialized: "
            f"price_change_threshold={price_change_threshold:.0%}, "
            f"complementary_threshold={complementary_threshold:.2f}"
        )

    def validate_price_update(
        self,
        position_id: str,
        token_id: str,
        entry_price: float,
        new_price: float,
    ) -> Optional[TokenConfusionAlert]:
        """
        验证价格更新是否合理

        Args:
            position_id: 持仓 ID
            token_id: Token ID
            entry_price: 入场价格
            new_price: 新价格

        Returns:
            TokenConfusionAlert 如果检测到混淆，否则 None
        """
        if entry_price <= 0:
            return None

        # 计算价格变化
        price_change_pct = abs(new_price - entry_price) / entry_price

        # 如果价格变化小于阈值，不进行检查
        if price_change_pct < self.price_change_threshold:
            return None

        # 进行混淆检测
        is_suspicious = False
        reasons = []

        # 1. 价格接近极端值检测
        if 0.3 < entry_price < 0.7:
            if new_price < 0.30 or new_price > 0.70:
                is_suspicious = True
                reasons.append(f"Price moved to extreme ({new_price:.4f}) from normal range ({entry_price:.4f})")

        # 2. 价格互补检测
        price_sum = new_price + entry_price
        if abs(price_sum - 1.0) < self.complementary_threshold:
            is_suspicious = True
            reasons.append(f"Prices are nearly complementary (sum={price_sum:.4f}, expected ~1.0)")

        # 3. 反向价格变化检测
        inverted_price = 1 - new_price
        inverted_entry = 1 - entry_price
        if inverted_entry != 0:
            inverted_change_pct = abs(inverted_price - inverted_entry) / inverted_entry
            if inverted_change_pct < price_change_pct and inverted_change_pct < 0.15:
                is_suspicious = True
                reasons.append(
                    f"Inverse price change ({inverted_change_pct:.2%}) is smaller than "
                    f"direct change ({price_change_pct:.2%})"
                )

        # 如果检测到可疑情况，生成警报
        if is_suspicious:
            self._detections += 1

            # 计算预期的正确价格范围（基于互补关系）
            expected_price_range = (1 - entry_price - 0.05, 1 - entry_price + 0.05)

            alert = TokenConfusionAlert(
                position_id=position_id,
                token_id=token_id,
                detected_price=new_price,
                expected_price_range=expected_price_range,
                confidence=min(price_change_pct * 100, 95.0),  # 置信度
                reason="; ".join(reasons),
                recommended_action="VERIFY_TOKEN_ID" if len(reasons) > 1 else "IGNORE_IF_CONFIRMED",
            )

            logger.warning(
                f"Token confusion DETECTED for {position_id}: "
                f"token={token_id}, price={new_price:.4f}, "
                f"entry={entry_price:.4f}, reasons={reasons}"
            )

            # 触发回调
            if self.on_confusion_detected:
                try:
                    self.on_confusion_detected(alert)
                except Exception as e:
                    logger.error(f"Error in confusion detection callback: {e}")

            return alert

        return None

    def mark_false_positive(self, position_id: str):
        """标记误报，用于改进检测算法"""
        self._false_positives += 1
        logger.debug(f"Marked detection for {position_id} as false positive")

    def get_stats(self) -> Dict:
        """获取检测统计信息"""
        total = self._detections + self._false_positives
        accuracy = ((self._detections - self._false_positives) / self._detections * 100) if self._detections > 0 else 0

        return {
            "total_detections": self._detections,
            "false_positives": self._false_positives,
            "accuracy": f"{accuracy:.1f}%",
            "price_change_threshold": self.price_change_threshold,
            "complementary_threshold": self.complementary_threshold,
        }
