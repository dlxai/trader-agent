"""
入场条件判断模块 (Entry Condition)

验证市场是否满足买入条件，包括：
- 价格区间检查（避免死亡区间 $0.60-$0.85）
- 流动性检查（最小 $1000）
- 到期时间检查（避免即将到期市场）
- 波动率检查（避免过高波动）
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, Tuple
import math
import logging


logger = logging.getLogger(__name__)


class EntryCheckResult(Enum):
    """入场检查结果枚举"""
    PASSED = auto()           # 通过
    FAILED_PRICE = auto()     # 价格检查失败
    FAILED_LIQUIDITY = auto() # 流动性检查失败
    FAILED_EXPIRY = auto()    # 到期时间检查失败
    FAILED_VOLATILITY = auto() # 波动率检查失败
    FAILED_GENERAL = auto()   # 一般性失败


@dataclass
class EntryCheckDetail:
    """入场检查详情"""
    check_name: str
    result: EntryCheckResult
    passed: bool
    message: str
    value: Any = None
    threshold: Any = None


@dataclass
class EntryValidationResult:
    """入场验证结果"""
    market_id: str
    can_enter: bool
    overall_result: EntryCheckResult
    checks: List[EntryCheckDetail] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def failed_checks(self) -> List[EntryCheckDetail]:
        """获取失败的检查"""
        return [c for c in self.checks if not c.passed]

    @property
    def pass_rate(self) -> float:
        """计算通过率"""
        if not self.checks:
            return 0.0
        return len([c for c in self.checks if c.passed]) / len(self.checks)


# ==================== 数据源协议 ====================

class MarketInfoSource(Protocol):
    """市场信息数据源协议"""
    def get_market_info(self, market_id: str) -> Dict[str, Any]:
        ...
    def get_market_expiry(self, market_id: str) -> Optional[datetime]:
        ...
    def get_market_category(self, market_id: str) -> Optional[str]:
        ...


class LiquiditySource(Protocol):
    """流动性数据源协议"""
    def get_available_liquidity(self, market_id: str) -> float:
        ...
    def get_order_book_depth(self, market_id: str) -> Dict[str, float]:
        ...


class VolatilitySource(Protocol):
    """波动率数据源协议"""
    def get_volatility(self, market_id: str, period: str = "24h") -> float:
        ...
    def get_price_range(self, market_id: str, period: str = "24h") -> Tuple[float, float]:
        ...


# ==================== 入场条件验证器 ====================

@dataclass
class EntryConditionConfig:
    """入场条件配置"""
    # 价格区间限制（避免死亡区间）
    price_min: float = 0.05
    price_max: float = 0.95
    death_zone_min: float = 0.60  # 死亡区间下界
    death_zone_max: float = 0.85  # 死亡区间上界
    allow_death_zone: bool = False  # 是否允许死亡区间交易

    # 流动性限制
    min_liquidity: float = 1000.0  # 最小流动性（USD）
    min_order_book_depth: float = 500.0  # 最小订单簿深度

    # 到期时间限制
    min_time_to_expiry: timedelta = field(default_factory=lambda: timedelta(hours=24))
    max_time_to_expiry: timedelta = field(default_factory=lambda: timedelta(days=365))
    avoid_expiry_within: timedelta = field(default_factory=lambda: timedelta(hours=6))

    # 波动率限制
    max_volatility: float = 0.50  # 最大日波动率（50%）
    min_volatility: float = 0.01  # 最小波动率（避免死市）

    # 评分阈值
    min_entry_score: float = 0.6  # 最小入场评分


class EntryConditionValidator:
    """入场条件验证器"""

    def __init__(
        self,
        market_source: MarketInfoSource,
        liquidity_source: LiquiditySource,
        volatility_source: VolatilitySource,
        config: Optional[EntryConditionConfig] = None,
    ):
        self.market_source = market_source
        self.liquidity_source = liquidity_source
        self.volatility_source = volatility_source
        self.config = config or EntryConditionConfig()

    def validate(self, market_id: str, current_price: Optional[float] = None) -> EntryValidationResult:
        """
        验证市场是否满足入场条件

        Args:
            market_id: 市场ID
            current_price: 当前价格（可选，如果提供则直接使用，否则从数据源获取）

        Returns:
            EntryValidationResult: 验证结果
        """
        checks = []

        try:
            # 1. 价格区间检查
            price_check = self._check_price_range(market_id, current_price)
            checks.append(price_check)

            # 2. 流动性检查
            liquidity_check = self._check_liquidity(market_id)
            checks.append(liquidity_check)

            # 3. 到期时间检查
            expiry_check = self._check_expiry(market_id)
            checks.append(expiry_check)

            # 4. 波动率检查
            volatility_check = self._check_volatility(market_id)
            checks.append(volatility_check)

        except Exception as e:
            logger.error(f"Error validating entry conditions for {market_id}: {e}", exc_info=True)
            checks.append(EntryCheckDetail(
                check_name="general",
                result=EntryCheckResult.FAILED_GENERAL,
                passed=False,
                message=f"Validation error: {str(e)}",
            ))

        # 确定总体结果
        failed_checks = [c for c in checks if not c.passed]
        can_enter = len(failed_checks) == 0

        if not can_enter:
            # 确定首要失败原因
            priority = [
                EntryCheckResult.FAILED_PRICE,
                EntryCheckResult.FAILED_LIQUIDITY,
                EntryCheckResult.FAILED_EXPIRY,
                EntryCheckResult.FAILED_VOLATILITY,
            ]
            overall_result = EntryCheckResult.FAILED_GENERAL
            for p in priority:
                if any(c.result == p for c in failed_checks):
                    overall_result = p
                    break
        else:
            overall_result = EntryCheckResult.PASSED

        return EntryValidationResult(
            market_id=market_id,
            can_enter=can_enter,
            overall_result=overall_result,
            checks=checks,
            timestamp=datetime.now(),
            metadata={
                "pass_rate": len([c for c in checks if c.passed]) / len(checks) if checks else 0,
                "total_checks": len(checks),
                "failed_count": len(failed_checks),
            }
        )

    def _check_price_range(self, market_id: str, current_price: Optional[float]) -> EntryCheckDetail:
        """检查价格区间"""
        try:
            # 获取当前价格
            price = current_price
            if price is None:
                # 从市场信息获取
                market_info = self.market_source.get_market_info(market_id)
                price = market_info.get("current_price", market_info.get("last_price", 0))

            if price is None or price <= 0:
                return EntryCheckDetail(
                    check_name="price_range",
                    result=EntryCheckResult.FAILED_PRICE,
                    passed=False,
                    message=f"Invalid price: {price}",
                    value=price,
                )

            # 检查基本范围
            if not (self.config.price_min <= price <= self.config.price_max):
                return EntryCheckDetail(
                    check_name="price_range",
                    result=EntryCheckResult.FAILED_PRICE,
                    passed=False,
                    message=f"Price {price:.4f} outside allowed range [{self.config.price_min:.2f}, {self.config.price_max:.2f}]",
                    value=price,
                    threshold=f"[{self.config.price_min:.2f}, {self.config.price_max:.2f}]",
                )

            # 检查死亡区间
            if not self.config.allow_death_zone:
                if self.config.death_zone_min <= price <= self.config.death_zone_max:
                    return EntryCheckDetail(
                        check_name="price_range",
                        result=EntryCheckResult.FAILED_PRICE,
                        passed=False,
                        message=f"Price {price:.4f} in death zone [{self.config.death_zone_min:.2f}, {self.config.death_zone_max:.2f}]",
                        value=price,
                        threshold=f"Exclude [{self.config.death_zone_min:.2f}, {self.config.death_zone_max:.2f}]",
                    )

            return EntryCheckDetail(
                check_name="price_range",
                result=EntryCheckResult.PASSED,
                passed=True,
                message=f"Price {price:.4f} within acceptable range",
                value=price,
            )

        except Exception as e:
            logger.error(f"Error checking price range for {market_id}: {e}")
            return EntryCheckDetail(
                check_name="price_range",
                result=EntryCheckResult.FAILED_GENERAL,
                passed=False,
                message=f"Price check error: {str(e)}",
            )

    def _check_liquidity(self, market_id: str) -> EntryCheckDetail:
        """检查流动性"""
        try:
            # 获取可用流动性
            available_liquidity = self.liquidity_source.get_available_liquidity(market_id)

            # 获取订单簿深度
            depth = self.liquidity_source.get_order_book_depth(market_id)
            bid_depth = depth.get("bid", 0)
            ask_depth = depth.get("ask", 0)
            total_depth = bid_depth + ask_depth

            # 检查最小流动性
            if available_liquidity < self.config.min_liquidity:
                return EntryCheckDetail(
                    check_name="liquidity",
                    result=EntryCheckResult.FAILED_LIQUIDITY,
                    passed=False,
                    message=f"Insufficient liquidity: ${available_liquidity:,.2f} < ${self.config.min_liquidity:,.2f}",
                    value=available_liquidity,
                    threshold=self.config.min_liquidity,
                )

            # 检查订单簿深度
            if total_depth < self.config.min_order_book_depth:
                return EntryCheckDetail(
                    check_name="liquidity",
                    result=EntryCheckResult.FAILED_LIQUIDITY,
                    passed=False,
                    message=f"Insufficient order book depth: ${total_depth:,.2f} < ${self.config.min_order_book_depth:,.2f}",
                    value=total_depth,
                    threshold=self.config.min_order_book_depth,
                )

            return EntryCheckDetail(
                check_name="liquidity",
                result=EntryCheckResult.PASSED,
                passed=True,
                message=f"Liquidity sufficient: ${available_liquidity:,.2f} available, ${total_depth:,.2f} depth",
                value={
                    "available_liquidity": available_liquidity,
                    "order_book_depth": total_depth,
                },
            )

        except Exception as e:
            logger.error(f"Error checking liquidity for {market_id}: {e}")
            return EntryCheckDetail(
                check_name="liquidity",
                result=EntryCheckResult.FAILED_GENERAL,
                passed=False,
                message=f"Liquidity check error: {str(e)}",
            )

    def _check_expiry(self, market_id: str) -> EntryCheckDetail:
        """检查到期时间"""
        try:
            # 获取市场到期时间
            expiry = self.market_source.get_market_expiry(market_id)

            if expiry is None:
                # 没有到期时间（永续市场）
                return EntryCheckDetail(
                    check_name="expiry",
                    result=EntryCheckResult.PASSED,
                    passed=True,
                    message="No expiry date (perpetual market)",
                )

            now = datetime.now()
            time_to_expiry = expiry - now

            # 检查是否即将到期（应避免）
            if time_to_expiry < self.config.avoid_expiry_within:
                return EntryCheckDetail(
                    check_name="expiry",
                    result=EntryCheckResult.FAILED_EXPIRY,
                    passed=False,
                    message=f"Market expires too soon: {time_to_expiry.total_seconds()/3600:.1f}h < {self.config.avoid_expiry_within.total_seconds()/3600:.1f}h",
                    value=time_to_expiry,
                    threshold=self.config.avoid_expiry_within,
                )

            # 检查最小到期时间
            if time_to_expiry < self.config.min_time_to_expiry:
                return EntryCheckDetail(
                    check_name="expiry",
                    result=EntryCheckResult.FAILED_EXPIRY,
                    passed=False,
                    message=f"Insufficient time to expiry: {time_to_expiry.total_seconds()/3600:.1f}h < {self.config.min_time_to_expiry.total_seconds()/3600:.1f}h",
                    value=time_to_expiry,
                    threshold=self.config.min_time_to_expiry,
                )

            # 检查最大到期时间（避免过长）
            if time_to_expiry > self.config.max_time_to_expiry:
                return EntryCheckDetail(
                    check_name="expiry",
                    result=EntryCheckResult.FAILED_EXPIRY,
                    passed=False,
                    message=f"Time to expiry too long: {time_to_expiry.days} days > {self.config.max_time_to_expiry.days} days",
                    value=time_to_expiry,
                    threshold=self.config.max_time_to_expiry,
                )

            return EntryCheckDetail(
                check_name="expiry",
                result=EntryCheckResult.PASSED,
                passed=True,
                message=f"Expiry time acceptable: {time_to_expiry.days} days, {time_to_expiry.seconds//3600} hours",
                value=time_to_expiry,
            )

        except Exception as e:
            logger.error(f"Error checking expiry for {market_id}: {e}")
            return EntryCheckDetail(
                check_name="expiry",
                result=EntryCheckResult.FAILED_GENERAL,
                passed=False,
                message=f"Expiry check error: {str(e)}",
            )

    def _check_volatility(self, market_id: str) -> EntryCheckDetail:
        """检查波动率"""
        try:
            # 获取波动率
            volatility = self.volatility_source.get_volatility(market_id, period="24h")

            # 检查波动率是否过高
            if volatility > self.config.max_volatility:
                return EntryCheckDetail(
                    check_name="volatility",
                    result=EntryCheckResult.FAILED_VOLATILITY,
                    passed=False,
                    message=f"Volatility too high: {volatility:.1%} > {self.config.max_volatility:.1%}",
                    value=volatility,
                    threshold=self.config.max_volatility,
                )

            # 检查波动率是否过低（市场不活跃）
            if volatility < self.config.min_volatility:
                return EntryCheckDetail(
                    check_name="volatility",
                    result=EntryCheckResult.FAILED_VOLATILITY,
                    passed=False,
                    message=f"Volatility too low (illiquid): {volatility:.2%} < {self.config.min_volatility:.2%}",
                    value=volatility,
                    threshold=self.config.min_volatility,
                )

            # 计算价格波动范围作为额外参考
            price_range = self.volatility_source.get_price_range(market_id, period="24h")
            range_ratio = (price_range[1] - price_range[0]) / price_range[0] if price_range[0] > 0 else 0

            return EntryCheckDetail(
                check_name="volatility",
                result=EntryCheckResult.PASSED,
                passed=True,
                message=f"Volatility acceptable: {volatility:.1%} (24h range: {range_ratio:.1%})",
                value={
                    "volatility": volatility,
                    "price_range_24h": price_range,
                    "range_ratio": range_ratio,
                },
            )

        except Exception as e:
            logger.error(f"Error checking volatility for {market_id}: {e}")
            return EntryCheckDetail(
                check_name="volatility",
                result=EntryCheckResult.FAILED_GENERAL,
                passed=False,
                message=f"Volatility check error: {str(e)}",
            )
