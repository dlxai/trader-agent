"""Order routes."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.order import Order
from src.models.position import Position
from src.models.portfolio import Portfolio
from src.models.user import User
from src.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderSummaryResponse,
    OrderListResponse,
    OrderCancelResponse,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post(
    "",
    response_model=ApiResponse[OrderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    request: OrderCreate,
    portfolio_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new order."""
    from uuid import uuid4

    # Verify portfolio access
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # Validate order type and side
    if request.side not in ["yes", "no", "buy", "sell"]:
        raise ValidationError("Invalid side", field="side")

    if request.order_type not in ["market", "limit", "stop", "stop_limit"]:
        raise ValidationError("Invalid order type", field="order_type")

    # For limit orders, price is required
    if request.order_type in ["limit", "stop_limit"] and request.price is None:
        raise ValidationError("Price is required for limit orders", field="price")

    # Calculate remaining size
    remaining_size = request.size

    # Create order
    order = Order(
        id=uuid4(),
        portfolio_id=portfolio_id,
        position_id=None,  # Will be set when executed
        strategy_id=request.strategy_id,
        market_id=request.market_id,
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        status="pending",
        size=request.size,
        filled_size=Decimal("0"),
        remaining_size=remaining_size,
        price=request.price,
        avg_fill_price=None,
        stop_price=request.stop_price,
        total_cost=Decimal("0"),
        total_fees=Decimal("0"),
        time_in_force=request.time_in_force or "GTC",
        expires_at=request.expires_at,
        client_order_id=request.client_order_id,
        expected_price=request.expected_price,
        slippage_percent=Decimal("0"),
        notes=request.notes,
        source=request.source or "manual",
        signal_id=request.signal_id,
        metadata=request.metadata,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    # TODO: Submit order to execution engine
    # For now, just return the pending order

    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order),
        message="Order created successfully",
    )


@router.get(
    "",
    response_model=ApiResponse[OrderListResponse],
)
async def list_orders(
    portfolio_id: Optional[UUID] = None,
    position_id: Optional[UUID] = None,
    status: Optional[str] = None,
    side: Optional[str] = None,
    symbol: Optional[str] = None,
    order_type: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List orders with filtering."""
    # Build query
    query = select(Order).join(Portfolio).where(
        Portfolio.user_id == current_user.id
    )

    # Apply filters
    if portfolio_id:
        query = query.where(Order.portfolio_id == portfolio_id)
    if position_id:
        query = query.where(Order.position_id == position_id)
    if status:
        query = query.where(Order.status == status)
    if side:
        query = query.where(Order.side == side)
    if symbol:
        query = query.where(Order.symbol.ilike(f"%{symbol}%"))
    if order_type:
        query = query.where(Order.order_type == order_type)
    if from_date:
        query = query.where(Order.created_at >= from_date)
    if to_date:
        query = query.where(Order.created_at <= to_date)

    # Order by created_at desc
    query = query.order_by(Order.created_at.desc())

    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    orders = result.scalars().all()

    # Convert to summary responses
    items = [
        OrderSummaryResponse(
            id=o.id,
            portfolio_id=o.portfolio_id,
            symbol=o.symbol,
            side=o.side,
            order_type=o.order_type,
            status=o.status,
            size=o.size,
            filled_size=o.filled_size,
            remaining_size=o.remaining_size,
            price=o.price,
            avg_fill_price=o.avg_fill_price,
            created_at=o.created_at,
            executed_at=o.executed_at,
        )
        for o in orders
    ]

    return ApiResponse(
        success=True,
        data=OrderListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{order_id}",
    response_model=ApiResponse[OrderResponse],
)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific order by ID."""
    result = await db.execute(
        select(Order).join(Portfolio).where(
            Order.id == order_id,
            Portfolio.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()

    if order is None:
        raise NotFoundError("Order", f"Order {order_id} not found")

    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order),
    )


@router.post(
    "/{order_id}/cancel",
    response_model=ApiResponse[OrderCancelResponse],
)
async def cancel_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Cancel a pending order."""
    result = await db.execute(
        select(Order).join(Portfolio).where(
            Order.id == order_id,
            Portfolio.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()

    if order is None:
        raise NotFoundError("Order", f"Order {order_id} not found")

    # Check if order can be cancelled
    if order.status not in ["pending", "open", "partially_filled"]:
        raise ValidationError(
            f"Cannot cancel order with status '{order.status}'",
            field="status",
        )

    # Cancel the order
    order.cancel()

    # Refund portfolio if order was partially filled
    if order.filled_size > 0:
        # Refund remaining balance
        portfolio = order.portfolio
        remaining_value = order.remaining_size * (order.avg_fill_price or order.price or Decimal("0"))
        portfolio.current_balance += remaining_value

    await db.commit()
    await db.refresh(order)

    return ApiResponse(
        success=True,
        data=OrderCancelResponse(
            order_id=order.id,
            status=order.status,
            cancelled_at=order.cancelled_at,
            filled_size=order.filled_size,
            remaining_size=order.remaining_size,
            message="Order cancelled successfully",
        ),
    )


# Need to add this import at the top of the file
from src.schemas.order import OrderSummaryResponse, OrderCancelResponse
