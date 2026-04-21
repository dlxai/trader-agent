"""Strategy schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Request Schemas ============

class StrategyCreate(BaseModel):
    """Strategy creation request."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    portfolio_id: UUID
    provider_id: Optional[UUID] = None

    # Prompt 配置
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None

    # 数据源配置
    data_sources: Optional[dict] = None

    # 下单金额配置
    min_order_size: Decimal = Field(default=Decimal("5"), ge=0)
    max_order_size: Decimal = Field(default=Decimal("50"), ge=0)

    # 市场过滤
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None

    # 执行间隔
    run_interval_minutes: int = Field(default=15, ge=1, le=1440)

    # 风险控制
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = None
    take_profit_percent: Optional[Decimal] = None


class StrategyUpdate(BaseModel):
    """Strategy update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    provider_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None
    data_sources: Optional[dict] = None
    min_order_size: Optional[Decimal] = Field(None, ge=0)
    max_order_size: Optional[Decimal] = Field(None, ge=0)
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None
    run_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = None
    take_profit_percent: Optional[Decimal] = None
    is_active: Optional[bool] = None


# ============ Response Schemas ============

class StrategyResponse(BaseModel):
    """Strategy response."""
    id: UUID
    user_id: UUID
    portfolio_id: Optional[UUID]
    provider_id: Optional[UUID]

    name: str
    description: Optional[str]
    type: str
    is_active: bool
    is_paused: bool
    status: str

    # AI 配置
    system_prompt: Optional[str]
    custom_prompt: Optional[str]
    data_sources: Optional[dict]

    # 下单金额
    min_order_size: Decimal
    max_order_size: Decimal

    # 市场过滤
    market_filter_days: Optional[int]
    market_filter_type: Optional[str]

    # 执行间隔
    run_interval_minutes: int
    last_run_at: Optional[datetime]
    total_runs: int

    # 风险控制
    max_position_size: Optional[Decimal]
    max_open_positions: Optional[int]
    stop_loss_percent: Optional[Decimal]
    take_profit_percent: Optional[Decimal]

    # 性能统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: Decimal
    sharpe_ratio: Optional[Decimal]

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategySummary(BaseModel):
    """Strategy summary for list view."""
    id: UUID
    name: str
    type: str
    is_active: bool
    status: str
    min_order_size: Decimal
    max_order_size: Decimal
    total_trades: int
    total_pnl: Decimal

    model_config = {"from_attributes": True}


class StrategyListResponse(BaseModel):
    """Strategy list response."""
    items: list[StrategySummary]
    total: int
    page: int
    page_size: int
