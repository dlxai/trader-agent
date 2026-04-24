"""Strategy schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID

from pydantic import Field, field_validator, model_validator, ConfigDict

from .base import BaseSchema, PaginatedResponse


class StrategyBase(BaseSchema):
    """Base strategy schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    portfolio_id: Optional[UUID] = None
    type: str = Field(..., min_length=1, max_length=50)
    provider_id: Optional[UUID] = None

    # Prompt 配置
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None

    # 数据源配置
    data_sources: Optional[Dict] = None

    # 触发条件配置
    trigger: Optional["StrategyTrigger"] = None

    # 信号过滤配置
    filters: Optional["StrategyFilters"] = None

    # 持仓监控配置
    position_monitor: Optional["StrategyPositionMonitor"] = None

    # 下单金额配置
    min_order_size: Decimal = Field(default=Decimal("1"), ge=0)
    max_order_size: Decimal = Field(default=Decimal("5"), ge=0)
    default_amount: Decimal = Field(default=Decimal("1"), ge=0)
    min_risk_reward_ratio: Optional[Decimal] = Field(default=Decimal("2.0"), ge=0)
    min_position_size: Decimal = Field(default=Decimal("1"), ge=0)
    max_position_size: Optional[Decimal] = Field(default=Decimal("5"), ge=0)

    # 市场过滤
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None
    allowed_markets: Optional[List] = None
    excluded_markets: Optional[List] = None
    min_liquidity: Optional[Decimal] = None
    max_spread_percent: Optional[Decimal] = None

    # 执行间隔
    run_interval_minutes: int = Field(default=15, ge=1, le=1440)
    order_type: str = Field(default="market")
    time_in_force: str = Field(default="GTC")
    slippage_tolerance: Decimal = Field(default=Decimal("0.001"), ge=0, le=0.1)
    trading_schedule: Optional[Dict] = None
    timezone: str = Field(default="UTC")

    # 风险控制
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    take_profit_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    trailing_stop_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    allocation_percent: Decimal = Field(default=Decimal("100"), ge=0, le=100)
    max_daily_loss: Optional[Decimal] = None
    max_weekly_loss: Optional[Decimal] = None

    # 配置与元数据
    config: Optional[Dict] = None
    parameters: Optional[Dict] = None
    strategy_metadata: Optional[Dict] = None
    parent_strategy_id: Optional[UUID] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"ai", "manual", "quant"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        allowed = {"market", "limit", "stop", "stop_limit"}
        if v not in allowed:
            raise ValueError(f"order_type must be one of {allowed}")
        return v

    @field_validator("time_in_force")
    @classmethod
    def validate_time_in_force(cls, v: str) -> str:
        allowed = {"GTC", "IOC", "FOK"}
        if v not in allowed:
            raise ValueError(f"time_in_force must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_amount_fields(self) -> "StrategyBase":
        """Validate amount field relationships."""
        errors = []

        # max_order_size >= min_order_size
        if self.max_order_size < self.min_order_size:
            errors.append(
                f"max_order_size ({self.max_order_size}) must be >= min_order_size ({self.min_order_size})"
            )
        # default_amount >= min_order_size
        if self.default_amount < self.min_order_size:
            errors.append(
                f"default_amount ({self.default_amount}) must be >= min_order_size ({self.min_order_size})"
            )
        # default_amount <= max_order_size (if it passes the first two checks)
        if not errors and self.default_amount > self.max_order_size:
            errors.append(
                f"default_amount ({self.default_amount}) must be <= max_order_size ({self.max_order_size})"
            )
        # min_position_size <= max_position_size (if max_position_size is set)
        if self.max_position_size is not None and self.min_position_size > self.max_position_size:
            errors.append(
                f"min_position_size ({self.min_position_size}) must be <= max_position_size ({self.max_position_size})"
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self


class StrategyCreate(StrategyBase):
    """Strategy creation request."""


class StrategyUpdate(BaseSchema):
    """Strategy update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    portfolio_id: Optional[UUID] = None
    provider_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None
    data_sources: Optional[Dict] = None
    trigger: Optional["StrategyTrigger"] = None
    filters: Optional["StrategyFilters"] = None
    position_monitor: Optional["StrategyPositionMonitor"] = None
    default_amount: Optional[Decimal] = Field(None, ge=0)
    min_risk_reward_ratio: Optional[Decimal] = Field(None, ge=0)
    max_margin_usage: Optional[Decimal] = Field(None, ge=0, le=1.0)
    min_position_size: Optional[Decimal] = Field(None, ge=0)
    min_order_size: Optional[Decimal] = Field(None, ge=0)
    max_order_size: Optional[Decimal] = Field(None, ge=0)
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None
    run_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    take_profit_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    trailing_stop_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    allocation_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    max_daily_loss: Optional[Decimal] = None
    max_weekly_loss: Optional[Decimal] = None
    order_type: Optional[str] = None
    time_in_force: Optional[str] = None
    slippage_tolerance: Optional[Decimal] = Field(None, ge=0, le=0.1)
    allowed_markets: Optional[List] = None
    excluded_markets: Optional[List] = None
    min_liquidity: Optional[Decimal] = None
    max_spread_percent: Optional[Decimal] = None
    trading_schedule: Optional[Dict] = None
    timezone: Optional[str] = None
    config: Optional[Dict] = None
    parameters: Optional[Dict] = None
    strategy_metadata: Optional[Dict] = None
    version: Optional[int] = None
    parent_strategy_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    is_paused: Optional[bool] = None
    status: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"ai", "manual", "quant"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"market", "limit", "stop", "stop_limit"}
        if v not in allowed:
            raise ValueError(f"order_type must be one of {allowed}")
        return v

    @field_validator("time_in_force")
    @classmethod
    def validate_time_in_force(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"GTC", "IOC", "FOK"}
        if v not in allowed:
            raise ValueError(f"time_in_force must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_amount_fields(self) -> "StrategyUpdate":
        """Validate amount field relationships when all fields are present."""
        # Only validate fields that are actually provided (not None)
        # max_order_size vs min_order_size
        if self.max_order_size is not None and self.min_order_size is not None:
            if self.max_order_size < self.min_order_size:
                raise ValueError(
                    f"max_order_size ({self.max_order_size}) must be >= min_order_size ({self.min_order_size})"
                )

        # default_amount vs min_order_size
        if self.default_amount is not None and self.min_order_size is not None:
            if self.default_amount < self.min_order_size:
                raise ValueError(
                    f"default_amount ({self.default_amount}) must be >= min_order_size ({self.min_order_size})"
                )

        # default_amount vs max_order_size
        if self.default_amount is not None and self.max_order_size is not None:
            if self.default_amount > self.max_order_size:
                raise ValueError(
                    f"default_amount ({self.default_amount}) must be <= max_order_size ({self.max_order_size})"
                )

        # min_position_size vs max_position_size (only if max_position_size is set)
        if self.min_position_size is not None and self.max_position_size is not None:
            if self.min_position_size > self.max_position_size:
                raise ValueError(
                    f"min_position_size ({self.min_position_size}) must be <= max_position_size ({self.max_position_size})"
                )

        return self


# ============ Response Schemas ============

class StrategyResponse(StrategyBase):
    """Strategy response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    is_active: bool
    is_paused: bool
    status: str

    # 运行统计
    last_run_at: Optional[datetime]
    total_runs: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: Decimal
    total_fees: Decimal
    sharpe_ratio: Optional[Decimal]
    max_drawdown: Optional[Decimal]

    version: int
    created_at: datetime
    updated_at: datetime


class StrategySummary(BaseSchema):
    """Strategy summary for list view."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str]
    type: str
    is_active: bool
    status: str
    portfolio_id: Optional[UUID] = None
    provider_id: Optional[UUID] = None
    min_order_size: Decimal
    max_order_size: Decimal
    total_trades: int
    total_pnl: Decimal
    run_interval_minutes: int
    created_at: datetime


class StrategyListResponse(PaginatedResponse[StrategySummary]):
    """Strategy list response."""


# ============ New Configuration Schemas ============


class StrategyFilters(BaseSchema):
    """Signal filtering configuration."""
    min_confidence: int = Field(default=40, ge=0, le=100)
    min_price: float = Field(default=0.50, ge=0, le=1)
    max_price: float = Field(default=0.99, ge=0, le=1)
    max_spread: float = Field(default=3.0, ge=0, le=100)
    max_slippage: float = Field(default=2.0, ge=0, le=100)
    dead_zone_enabled: bool = Field(default=True)
    dead_zone_min: float = Field(default=0.60, ge=0, le=1)
    dead_zone_max: float = Field(default=0.85, ge=0, le=1)
    keywords_exclude: List[str] = Field(default_factory=lambda: ["o/u", "spread"])

    # 到期时间过滤（来自 polymarket-agent）
    # 超过这个小时数的市场不交易
    # 通用策略：6（超过6小时忽略）
    # 尾盘策略：2（超过2小时忽略）
    max_hours_to_expiry: float = Field(default=6.0)


class StrategyPositionMonitor(BaseSchema):
    """Position monitoring configuration."""
    enable_stop_loss: bool = Field(default=True)
    stop_loss_percent: float = Field(default=-15.0, le=0)
    enable_take_profit: bool = Field(default=True)
    take_profit_price: float = Field(default=0.999, ge=0, le=1)
    enable_trailing_stop: bool = Field(default=True)
    trailing_stop_percent: float = Field(default=5.0, ge=0, le=100)
    enable_auto_redeem: bool = Field(default=True)


class StrategyTrigger(BaseSchema):
    """Trigger configuration."""
    price_change_threshold: float = Field(default=5.0, ge=0, le=100)
    activity_netflow_threshold: float = Field(default=1000.0, ge=0)
    min_trigger_interval: int = Field(default=5, ge=1, le=1440)
    scan_interval: int = Field(default=15, ge=1, le=1440)


class StrategyDataSources(BaseSchema):
    """Data sources configuration."""
    enable_market_data: bool = Field(default=True)
    enable_activity: bool = Field(default=True)
    enable_sports_score: bool = Field(default=True)


# Update forward references
StrategyTrigger.model_rebuild()
StrategyFilters.model_rebuild()
StrategyPositionMonitor.model_rebuild()
StrategyDataSources.model_rebuild()
