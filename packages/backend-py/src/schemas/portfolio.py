"""Portfolio schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field, field_validator, ConfigDict

from .base import BaseSchema, PaginatedResponse


class PortfolioBase(BaseSchema):
    """Base portfolio schema."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    # Settings
    trading_mode: str = Field(default="paper")  # paper, live
    risk_level: str = Field(default="medium")  # low, medium, high

    # Limits
    max_position_size: Optional[Decimal] = Field(None, ge=0)
    max_open_positions: Optional[int] = Field(None, ge=0)
    stop_loss_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    take_profit_percent: Optional[Decimal] = Field(None, ge=0, le=100)

    @field_validator("trading_mode")
    @classmethod
    def validate_trading_mode(cls, v: str) -> str:
        allowed = {"paper", "live"}
        if v not in allowed:
            raise ValueError(f"trading_mode must be one of {allowed}")
        return v

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        allowed = {"low", "medium", "high"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}")
        return v


class PortfolioCreate(PortfolioBase):
    """Portfolio creation schema."""

    initial_balance: Decimal = Field(default=Decimal("0"), ge=0)


class PortfolioUpdate(BaseSchema):
    """Portfolio update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    is_paused: Optional[bool] = None
    risk_level: Optional[str] = None
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = None
    take_profit_percent: Optional[Decimal] = None

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"low", "medium", "high"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}")
        return v


class PortfolioResponse(PortfolioBase):
    """Portfolio response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    is_active: bool
    is_default: bool
    is_paused: bool

    # Balance
    initial_balance: Decimal
    current_balance: Decimal
    total_deposited: Decimal
    total_withdrawn: Decimal

    # Performance
    total_pnl: Decimal
    total_pnl_percent: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int

    # Timestamps
    created_at: datetime
    updated_at: datetime


class PortfolioSummaryResponse(BaseSchema):
    """Portfolio summary for list views."""

    id: UUID
    name: str
    trading_mode: str
    is_active: bool
    current_balance: Decimal
    total_pnl: Decimal
    total_pnl_percent: Decimal
    total_trades: int
    strategy_count: int = 0
    strategy_total_pnl: Decimal = Decimal("0")
    created_at: datetime


class PortfolioListResponse(BaseSchema):
    """Portfolio list response."""

    items: List[PortfolioSummaryResponse]
    total: int
    page: int
    page_size: int


class PortfolioDepositRequest(BaseSchema):
    """Portfolio deposit request."""

    amount: Decimal = Field(..., gt=0)
    source: str = Field(default="manual")
    notes: Optional[str] = None


class PortfolioWithdrawRequest(BaseSchema):
    """Portfolio withdrawal request."""

    amount: Decimal = Field(..., gt=0)
    destination: str = Field(default="manual")
    notes: Optional[str] = None


class PortfolioPerformanceResponse(BaseSchema):
    """Portfolio performance metrics."""

    portfolio_id: UUID
    period: str  # 1d, 7d, 30d, 90d, 1y, all

    # Returns
    total_return: Decimal
    total_return_percent: Decimal
    annualized_return: Optional[Decimal]

    # Risk metrics
    volatility: Optional[Decimal]
    sharpe_ratio: Optional[Decimal]
    sortino_ratio: Optional[Decimal]
    max_drawdown: Optional[Decimal]
    max_drawdown_percent: Optional[Decimal]

    # Trading metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    avg_profit: Decimal
    avg_loss: Decimal
    profit_factor: Optional[Decimal]

    # Benchmark
    benchmark_return: Optional[Decimal]
    alpha: Optional[Decimal]
    beta: Optional[Decimal]

    # Time series data (for charts)
    equity_curve: Optional[List[dict]]  # List of {timestamp, equity}
    daily_returns: Optional[List[dict]]  # List of {date, return}

    generated_at: datetime
