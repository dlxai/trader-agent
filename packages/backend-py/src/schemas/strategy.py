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
    """信号过滤配置"""
    # 基础过滤
    min_signal_confidence: Optional[Decimal] = Field(default=Decimal("0.5"), ge=0, le=1.0)
    max_slippage_percent: Optional[Decimal] = Field(default=Decimal("0.5"), ge=0, le=10)
    min_volume: Optional[Decimal] = None
    min_market_cap: Optional[Decimal] = None
    exclude_volatile: bool = Field(default=False)
    volatility_threshold: Optional[Decimal] = Field(default=Decimal("5"), ge=0, le=100)

    # 时间过滤
    avoid_market_open_minutes: Optional[int] = Field(default=15, ge=0)
    avoid_market_close_minutes: Optional[int] = Field(default=15, ge=0)
    trading_days_only: bool = Field(default=True)

    # 信号聚合
    require_multiple_signals: bool = Field(default=False)
    min_signal_count: int = Field(default=2, ge=1)
    signal_window_minutes: int = Field(default=60, ge=1)

    # 新闻/事件过滤
    check_news_sentiment: bool = Field(default=False)
    max_negative_news_score: Optional[Decimal] = Field(default=Decimal("-0.5"), le=0)

    # 相关性过滤
    avoid_correlated_positions: bool = Field(default=False)
    max_correlation: Decimal = Field(default=Decimal("0.7"), ge=0, le=1.0)
    correlation_lookback_days: int = Field(default=30, ge=1)


class StrategyPositionMonitor(BaseSchema):
    """持仓监控配置"""
    # 持仓限制
    max_positions_per_market: int = Field(default=3, ge=1)
    max_positions_per_asset: int = Field(default=1, ge=1)
    max_correlated_positions: int = Field(default=2, ge=1)

    # 风险监控
    auto_close_on_max_loss: bool = Field(default=False)
    max_total_loss_percent: Optional[Decimal] = Field(default=Decimal("10"), ge=0, le=100)
    auto_close_on_drawdown: bool = Field(default=False)
    max_drawdown_percent: Optional[Decimal] = Field(default=Decimal("20"), ge=0, le=100)

    # 预警设置
    enable_alerts: bool = Field(default=True)
    alert_threshold_percent: Decimal = Field(default=Decimal("5"), ge=0, le=100)

    # 分批平仓
    partial_close_enabled: bool = Field(default=False)
    partial_close_threshold: Decimal = Field(default=Decimal("3"), ge=0)
    partial_close_percent: Decimal = Field(default=Decimal("50"), ge=0, le=100)

    # 持仓时间限制
    max_holding_period_hours: Optional[int] = None
    auto_close_on_time: bool = Field(default=False)


class StrategyTrigger(BaseSchema):
    """触发条件配置"""
    # 触发类型
    trigger_type: str = Field(default="signal")
    allowed_triggers: List[str] = Field(default_factory=lambda: ["signal", "schedule", "event", "manual"])

    # 信号触发
    signal_source: Optional[str] = None
    signal_indicator: Optional[str] = None
    signal_condition: Optional[str] = None
    signal_threshold: Optional[Decimal] = None

    # 定时触发
    schedule_cron: Optional[str] = None
    schedule_interval_minutes: Optional[int] = Field(default=60, ge=1)
    schedule_timezone: str = Field(default="UTC")

    # 事件触发
    event_type: Optional[str] = None
    event_conditions: Optional[Dict] = None

    # 批量触发
    batch_signals: bool = Field(default=False)
    batch_size: int = Field(default=1, ge=1)
    batch_window_seconds: int = Field(default=60, ge=1)

    # 冷却时间
    cooldown_enabled: bool = Field(default=True)
    cooldown_minutes: int = Field(default=30, ge=0)
    cooldown_per_asset: bool = Field(default=True)

    # 触发限制
    max_triggers_per_run: int = Field(default=5, ge=1)
    max_daily_triggers: Optional[int] = Field(default=20, ge=1)


class StrategyDataSources(BaseSchema):
    """数据源配置"""
    # 价格数据
    price_source: str = Field(default="primary")
    price_sources_fallback: List[str] = Field(default_factory=list)
    price_update_frequency_seconds: int = Field(default=60, ge=1)

    # 市场数据
    market_data_source: str = Field(default="default")
    include_orderbook: bool = Field(default=False)
    orderbook_depth: int = Field(default=10, ge=1, le=50)

    # 技术指标
    indicators_source: str = Field(default="default")
    indicator_timeframes: List[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])
    include_custom_indicators: bool = Field(default=False)

    # 新闻和情绪
    news_source: Optional[str] = None
    sentiment_source: Optional[str] = None
    news_lookback_hours: int = Field(default=24, ge=1)

    # 社交/链上数据
    social_source: Optional[str] = None
    onchain_source: Optional[str] = None
    social_lookback_hours: int = Field(default=6, ge=1)

    # 备用源
    fallback_enabled: bool = Field(default=True)
    fallback_timeout_seconds: int = Field(default=10, ge=1)


# Update forward references
StrategyTrigger.model_rebuild()
StrategyFilters.model_rebuild()
StrategyPositionMonitor.model_rebuild()
StrategyDataSources.model_rebuild()
