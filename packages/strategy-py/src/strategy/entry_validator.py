"""
入场验证器 (Entry Validator)
验证买入条件，包括禁止交易区间检查
"""

import logging
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum

from config.settings import settings

logger = logging.getLogger(__name__)


class EntryRejectionReason(Enum):
    """入场被拒绝的原因"""
    NONE = "none"
    PRICE_IN_NO_TRADE_ZONE = "price_in_no_trade_zone"  # 价格在禁止交易区间
    PRICE_TOO_LOW = "price_too_low"  # 价格过低
    PRICE_TOO_HIGH = "price_too_high"  # 价格过高
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"  # 流动性不足
    EXPIRES_TOO_SOON = "expires_too_soon"  # 即将到期
    MARKET_CLOSED = "market_closed"  # 市场已关闭


@dataclass
class EntryValidationResult:
    """入场验证结果"""
    can_enter: bool
    rejection_reason: EntryRejectionReason
    message: str
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class EntryValidator:
    """
    入场验证器

    职责：
    1. 检查价格是否在禁止交易区间（死亡区间）
    2. 检查市场基本条件（流动性、到期时间等）
    3. 验证入场价格合理性
    """

    def __init__(self):
        self.no_trade_zones = settings.no_trade_zones
        self.min_price = 0.01  # 最低入场价
        self.max_price = 0.99  # 最高入场价

        logger.info(f"EntryValidator initialized with {len(self.no_trade_zones)} no-trade zones")

    def validate_entry(
        self,
        current_price: float,
        market_id: str,
        sec_to_expiry: Optional[int] = None,
        liquidity: Optional[float] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
    ) -> EntryValidationResult:
        """
        验证是否可以入场

        Args:
            current_price: 当前价格
            market_id: 市场ID
            sec_to_expiry: 距离到期的时间（秒）
            liquidity: 流动性（美元）
            best_bid: 最优买单价
            best_ask: 最优卖单价

        Returns:
            EntryValidationResult: 验证结果
        """
        # 1. 检查禁止交易区间（死亡区间）
        zone_result = self._check_no_trade_zones(current_price)
        if not zone_result.can_enter:
            return zone_result

        # 2. 检查价格范围
        if current_price < self.min_price:
            return EntryValidationResult(
                can_enter=False,
                rejection_reason=EntryRejectionReason.PRICE_TOO_LOW,
                message=f"Price {current_price:.4f} is below minimum {self.min_price}",
                metadata={"current_price": current_price, "min_price": self.min_price}
            )

        if current_price > self.max_price:
            return EntryValidationResult(
                can_enter=False,
                rejection_reason=EntryRejectionReason.PRICE_TOO_HIGH,
                message=f"Price {current_price:.4f} is above maximum {self.max_price}",
                metadata={"current_price": current_price, "max_price": self.max_price}
            )

        # 3. 检查到期时间（只用于筛选市场，不用于强制退出持仓）
        if sec_to_expiry is not None and sec_to_expiry <= 0:
            return EntryValidationResult(
                can_enter=False,
                rejection_reason=EntryRejectionReason.EXPIRES_TOO_SOON,
                message=f"Market has expired (sec_to_expiry={sec_to_expiry})",
                metadata={"sec_to_expiry": sec_to_expiry}
            )

        # 4. 检查流动性
        if liquidity is not None and liquidity < 1000:  # 最低$1000流动性
            return EntryValidationResult(
                can_enter=False,
                rejection_reason=EntryRejectionReason.INSUFFICIENT_LIQUIDITY,
                message=f"Insufficient liquidity: ${liquidity:.2f} (min $1000)",
                metadata={"liquidity": liquidity, "min_liquidity": 1000}
            )

        # 所有检查通过
        return EntryValidationResult(
            can_enter=True,
            rejection_reason=EntryRejectionReason.NONE,
            message="Entry validation passed",
            metadata={
                "current_price": current_price,
                "market_id": market_id,
                "sec_to_expiry": sec_to_expiry,
                "liquidity": liquidity,
            }
        )

    def _check_no_trade_zones(self, price: float) -> EntryValidationResult:
        """
        检查价格是否在禁止交易区间内

        Args:
            price: 当前价格

        Returns:
            EntryValidationResult: 验证结果
        """
        for zone in self.no_trade_zones:
            min_price = zone.get("min", 0.0)
            max_price = zone.get("max", 1.0)
            reason = zone.get("reason", "no_trade_zone")

            if min_price <= price <= max_price:
                return EntryValidationResult(
                    can_enter=False,
                    rejection_reason=EntryRejectionReason.PRICE_IN_NO_TRADE_ZONE,
                    message=f"Price {price:.4f} is in no-trade zone [{min_price:.2f}, {max_price:.2f}]: {reason}",
                    metadata={
                        "price": price,
                        "zone_min": min_price,
                        "zone_max": max_price,
                        "zone_reason": reason,
                    }
                )

        # 不在任何禁止区间内
        return EntryValidationResult(
            can_enter=True,
            rejection_reason=EntryRejectionReason.NONE,
            message="Price is outside all no-trade zones",
            metadata={"price": price}
        )

    def update_no_trade_zones(self, zones: List[Dict]):
        """
        更新禁止交易区间

        Args:
            zones: 新的禁止交易区间列表
        """
        self.no_trade_zones = zones
        logger.info(f"Updated no-trade zones: {len(zones)} zones")

    def get_no_trade_zones(self) -> List[Dict]:
        """获取当前禁止交易区间"""
        return self.no_trade_zones
