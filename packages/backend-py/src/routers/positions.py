"""Position routes."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.position import Position
from src.models.portfolio import Portfolio
from src.models.user import User
from src.schemas.position import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionSummaryResponse,
    PositionListResponse,
    PositionCloseRequest,
    PositionCloseResponse,
    PositionAdjustRequest,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.exceptions import NotFoundError, ValidationError, AuthorizationError

router = APIRouter(prefix="/api/positions", tags=["positions"])


async def verify_portfolio_access(
    portfolio_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Portfolio:
    """Verify user has access to portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == user_id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    return portfolio


@router.post(
    "",
    response_model=ApiResponse[PositionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_position(
    request: PositionCreate,
    portfolio_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new position."""
    from uuid import uuid4

    # Verify portfolio access
    portfolio = await verify_portfolio_access(portfolio_id, current_user.id, db)

    # Validate side
    if request.side not in ["yes", "no"]:
        raise ValidationError("Invalid side. Must be 'yes' or 'no'", field="side")

    # Create position
    position = Position(
        id=uuid4(),
        portfolio_id=portfolio_id,
        strategy_id=request.strategy_id,
        market_id=request.market_id,
        symbol=request.symbol,
        market_slug=request.market_slug,
        condition_id=request.condition_id,
        side=request.side,
        status="open",
        size=request.size,
        entry_price=request.entry_price,
        current_price=request.entry_price,
        average_entry_price=request.entry_price,
        opened_at=datetime.utcnow(),
        stop_loss_price=request.stop_loss_price,
        take_profit_price=request.take_profit_price,
        leverage=request.leverage,
        notes=request.notes,
        source=request.source,
        signal_id=request.signal_id,
    )

    # Calculate initial unrealized PnL (should be 0)
    position.unrealized_pnl = Decimal("0")
    position.total_pnl = Decimal("0")
    position.pnl_percent = Decimal("0")

    db.add(position)

    # Update portfolio
    portfolio.current_balance -= (request.entry_price * request.size)

    await db.commit()
    await db.refresh(position)

    return ApiResponse(
        success=True,
        data=PositionResponse.model_validate(position),
        message="Position created successfully",
    )


@router.get(
    "",
    response_model=ApiResponse[PositionListResponse],
)
async def list_positions(
    portfolio_id: Optional[UUID] = None,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List positions with filtering."""
    # Build query
    query = select(Position).join(Portfolio).where(
        Portfolio.user_id == current_user.id
    )

    # Apply filters
    if portfolio_id:
        query = query.where(Position.portfolio_id == portfolio_id)
    if status:
        query = query.where(Position.status == status)
    if symbol:
        query = query.where(Position.symbol.ilike(f"%{symbol}%"))
    if side:
        query = query.where(Position.side == side)

    # Order by opened_at desc
    query = query.order_by(Position.opened_at.desc())

    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    positions = result.scalars().all()

    # Convert to summary responses
    items = [
        PositionSummaryResponse(
            id=p.id,
            market_id=p.market_id,
            symbol=p.symbol,
            side=p.side,
            status=p.status,
            size=p.size,
            entry_price=p.entry_price,
            current_price=p.current_price,
            unrealized_pnl=p.unrealized_pnl,
            pnl_percent=p.pnl_percent,
            opened_at=p.opened_at,
            leverage=p.leverage,
        )
        for p in positions
    ]

    return ApiResponse(
        success=True,
        data=PositionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{position_id}",
    response_model=ApiResponse[PositionResponse],
)
async def get_position(
    position_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific position by ID."""
    result = await db.execute(
        select(Position).join(Portfolio).where(
            Position.id == position_id,
            Portfolio.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()

    if position is None:
        raise NotFoundError("Position", f"Position {position_id} not found")

    return ApiResponse(
        success=True,
        data=PositionResponse.model_validate(position),
    )


@router.put(
    "/{position_id}",
    response_model=ApiResponse[PositionResponse],
)
async def update_position(
    position_id: UUID,
    request: PositionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a position (risk parameters, notes, etc.)."""
    result = await db.execute(
        select(Position).join(Portfolio).where(
            Position.id == position_id,
            Portfolio.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()

    if position is None:
        raise NotFoundError("Position", f"Position {position_id} not found")

    if position.status != "open":
        raise ValidationError("Cannot update a closed position")

    # Update fields
    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "close_notes":
            continue  # Handle separately for close operation
        setattr(position, field, value)

    await db.commit()
    await db.refresh(position)

    return ApiResponse(
        success=True,
        data=PositionResponse.model_validate(position),
        message="Position updated successfully",
    )


@router.post(
    "/{position_id}/close",
    response_model=ApiResponse[PositionCloseResponse],
)
async def close_position(
    position_id: UUID,
    request: PositionCloseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Close a position."""
    from decimal import Decimal

    result = await db.execute(
        select(Position).join(Portfolio).where(
            Position.id == position_id,
            Portfolio.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()

    if position is None:
        raise NotFoundError("Position", f"Position {position_id} not found")

    if position.status != "open":
        raise ValidationError("Position is already closed")

    # Get exit price
    exit_price = request.exit_price
    if exit_price is None:
        # Use current market price
        exit_price = position.current_price

    # Calculate realized PnL
    position.exit_price = exit_price
    position.closed_at = datetime.utcnow()
    position.status = "closed"

    if position.side == "yes":
        position.realized_pnl = (exit_price - position.entry_price) * position.size
    else:
        position.realized_pnl = (position.entry_price - exit_price) * position.size

    position.total_pnl = position.realized_pnl + position.unrealized_pnl

    # Calculate percentage
    if position.entry_price > 0:
        position.pnl_percent = (position.total_pnl / (position.entry_price * position.size)) * 100

    # Update portfolio
    portfolio = position.portfolio
    portfolio.current_balance += (exit_price * position.size)
    portfolio.total_pnl += position.realized_pnl
    portfolio.total_trades += 1

    if position.realized_pnl > 0:
        portfolio.winning_trades += 1
    else:
        portfolio.losing_trades += 1

    # Recalculate portfolio PnL percentage
    if portfolio.initial_balance > 0:
        portfolio.total_pnl_percent = (
            portfolio.total_pnl / portfolio.initial_balance
        ) * 100

    await db.commit()
    await db.refresh(position)

    return ApiResponse(
        success=True,
        data=PositionCloseResponse(
            position_id=position.id,
            portfolio_id=portfolio.id,
            closed_size=position.size,
            exit_price=exit_price,
            realized_pnl=position.realized_pnl,
            total_pnl=position.total_pnl,
            pnl_percent=position.pnl_percent,
            total_fees=position.total_fees,
            closed_at=position.closed_at,
            remaining_position=None,
        ),
        message="Position closed successfully",
    )
