"""Order schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field, ConfigDict

from .base import BaseSchema, PaginatedResponse


class OrderBase(BaseSchema):
    """Base order schema."""

    market_id: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=50)
    side: str = Field(...)  # "yes" or "no"
    order_type: str = Field(default="market")  # market, limit, stop, stop_limit


class OrderCreate(OrderBase):
    """Order creation schema."""

    size: Decimal = Field(..., gt=0)
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: str = Field(default="GTC")
    expires_at: Optional[datetime] = None
    strategy_id: Optional[UUID] = None
    signal_id: Optional[str] = None
    notes: Optional[str] = None

    # Risk parameters
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None


class OrderUpdate(BaseSchema):
    """Order update schema."""

    # Only allow updating certain fields before execution
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    size: Optional[Decimal] = Field(None, gt=0)
    expires_at: Optional[datetime] = None
    notes: Optional[str] = None

    # Risk updates
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None


class OrderResponse(OrderBase):
    """Order response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    position_id: Optional[UUID] = None
    strategy_id: Optional[UUID] = None

    # Size and pricing
    size: Decimal
    filled_size: Decimal
    remaining_size: Decimal
    price: Optional[Decimal] = None
    avg_fill_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None

    # Status
    status: str  # pending, open, partially_filled, filled, cancelled, rejected, expired
    time_in_force: str

    # Costs
    total_cost: Decimal
    total_fees: Decimal
    fee_currency: str

    # Risk
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    # Timing
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # External IDs
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None

    # Source
    signal_id: Optional[str] = None
    source: str
    notes: Optional[str] = None
    order_metadata: Optional[dict] = None


class OrderSummaryResponse(BaseSchema):
    """Order summary for list views."""

    id: UUID
    market_id: str
    symbol: str
    side: str
    order_type: str
    size: Decimal
    filled_size: Decimal
    status: str
    created_at: datetime
    avg_fill_price: Optional[Decimal] = None


class OrderListResponse(PaginatedResponse[OrderSummaryResponse]):
    """Paginated order list response."""
    pass


class OrderCancelResponse(BaseSchema):
    """Order cancellation response."""

    success: bool
    order_id: UUID
    status: str
    message: str
    cancelled_at: datetime
