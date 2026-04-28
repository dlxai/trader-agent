"""Position schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field, ConfigDict

from .base import BaseSchema, PaginatedResponse


class PositionBase(BaseSchema):
    """Base position schema."""

    market_id: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=50)
    market_slug: Optional[str] = Field(None, max_length=100)
    condition_id: Optional[str] = Field(None, max_length=100)

    side: str = Field(...)  # "yes" or "no"


class PositionCreate(PositionBase):
    """Position creation schema."""

    size: Decimal = Field(..., gt=0)
    entry_price: Decimal = Field(..., gt=0)
    strategy_id: Optional[UUID] = None

    # Risk parameters
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    leverage: Decimal = Field(default=Decimal("1"), ge=1)

    notes: Optional[str] = None
    source: str = Field(default="manual")
    signal_id: Optional[str] = None


class PositionUpdate(BaseSchema):
    """Position update schema."""

    # Update risk parameters
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    trailing_stop_price: Optional[Decimal] = None

    # Close position
    exit_price: Optional[Decimal] = None
    close_notes: Optional[str] = None

    # Metadata
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class PositionResponse(PositionBase):
    """Position response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    strategy_id: Optional[UUID]

    # Size and pricing
    size: Decimal
    entry_price: Decimal
    exit_price: Optional[Decimal]
    current_price: Decimal
    average_entry_price: Decimal

    # P&L
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    pnl_percent: Decimal

    # Fees
    total_fees: Decimal
    funding_paid: Decimal
    funding_received: Decimal

    # Risk
    stop_loss_price: Optional[Decimal]
    take_profit_price: Optional[Decimal]
    liquidation_price: Optional[Decimal]
    margin_used: Optional[Decimal]
    leverage: Decimal

    # Status
    status: str  # open, closed, liquidated

    # Timestamps
    opened_at: datetime
    closed_at: Optional[datetime]
    last_updated_at: datetime
    created_at: datetime
    updated_at: datetime

    # Metadata
    notes: Optional[str]
    source: str
    signal_id: Optional[str]
    metadata: Optional[dict]
    market_name: Optional[str] = None


class PortfolioMini(BaseSchema):
    """Minimal portfolio info for embedding in other responses."""

    id: UUID
    name: str


class PositionSummaryResponse(BaseSchema):
    """Position summary for list views."""

    id: UUID
    market_id: str
    symbol: str
    side: str
    status: str

    size: Decimal
    entry_price: Decimal
    current_price: Decimal

    unrealized_pnl: Decimal
    pnl_percent: Decimal

    opened_at: datetime
    leverage: Decimal
    market_name: Optional[str] = None
    title: Optional[str] = None
    outcome: Optional[str] = None
    portfolio: Optional[PortfolioMini] = None


class PositionListResponse(BaseSchema):
    """Position list response."""

    items: List[PositionSummaryResponse]
    total: int
    page: int
    page_size: int


class PositionCloseRequest(BaseSchema):
    """Position close request."""

    exit_price: Optional[Decimal] = None  # If not provided, use market price
    size: Optional[Decimal] = None  # If not provided, close entire position
    notes: Optional[str] = None
    order_type: str = Field(default="market")  # market, limit


class PositionCloseResponse(BaseSchema):
    """Position close response."""

    position_id: UUID
    portfolio_id: UUID

    closed_size: Decimal
    exit_price: Decimal

    realized_pnl: Decimal
    total_pnl: Decimal
    pnl_percent: Decimal

    total_fees: Decimal

    closed_at: datetime

    remaining_position: Optional[dict]  # If partial close


class PositionAdjustRequest(BaseSchema):
    """Position size adjustment request."""

    action: str = Field(...)  # "increase" or "decrease"
    size: Decimal = Field(..., gt=0)
    price: Optional[Decimal] = None  # For limit orders
    order_type: str = Field(default="market")


class PositionHistoryResponse(BaseSchema):
    """Position history/audit trail."""

    position_id: UUID

    events: List[dict]  # List of position events
    # Event types: opened, size_increased, size_decreased, stop_loss_set,
    #              take_profit_set, partial_closed, fully_closed, liquidated

    total_events: int
    generated_at: datetime
