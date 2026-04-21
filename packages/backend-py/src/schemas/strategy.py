"""Strategy schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID

from pydantic import Field, field_validator, ConfigDict

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
    min_order_size: Decimal = Field(default=Decimal("5"), ge=0)
    max_order_size: Decimal = Field(default=Decimal("50"), ge=0)
    default_amount: Decimal = Field(default=Decimal("5"), ge=0)
    min_risk_reward_ratio: Optional[Decimal] = Field(default=Decimal("2.0"), ge=0)
    max_margin_usage: Decimal = Field(default=Decimal("0.9"), ge=0, le=1.0)
    min_position_size: Decimal = Field(default=Decimal("12"), ge=0)

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
    min_price: Decimal = Field(default=Decimal("0.50"), ge=0, le=1)
    max_price: Decimal = Field(default=Decimal("0.99"), ge=0, le=1)
    max_spread: Decimal = Field(default=Decimal("3"), ge=0, le=100)
    max_slippage: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    dead_zone_enabled: bool = Field(default=True)
    dead_zone_min: Decimal = Field(default=Decimal("0.70"), ge=0, le=1)
    dead_zone_max: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    keywords_exclude: List[str] = Field(default_factory=lambda: ["o/u", "spread"])


class StrategyPositionMonitor(BaseSchema):
    """Position monitoring configuration."""
    enable_stop_loss: bool = Field(default=True)
    stop_loss_percent: Decimal = Field(default=Decimal("-15"), le=0)
    enable_take_profit: bool = Field(default=True)
    take_profit_price: Decimal = Field(default=Decimal("0.999"), ge=0, le=1)
    enable_trailing_stop: bool = Field(default=True)
    trailing_stop_percent: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    enable_auto_redeem: bool = Field(default=True)


class StrategyTrigger(BaseSchema):
    """Trigger configuration."""
    price_change_threshold: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    activity_netflow_threshold: Decimal = Field(default=Decimal("1000"), ge=0)
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
