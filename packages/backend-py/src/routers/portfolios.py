"""Portfolio routes."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.portfolio import Portfolio
from src.models.user import User
from src.schemas.portfolio import (
    PortfolioCreate,
    PortfolioUpdate,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PortfolioListResponse,
    PortfolioDepositRequest,
    PortfolioWithdrawRequest,
    PortfolioPerformanceResponse,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@router.post(
    "",
    response_model=ApiResponse[PortfolioResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio(
    request: PortfolioCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new portfolio."""
    from uuid import uuid4

    # Check if user wants this as default and unset others
    if request.is_default if hasattr(request, 'is_default') else False:
        await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.is_default == True
            )
        )
        # Unset default on all others
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.is_default == True
            )
        )
        for portfolio in result.scalars().all():
            portfolio.is_default = False

    portfolio = Portfolio(
        id=uuid4(),
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        initial_balance=request.initial_balance,
        current_balance=request.initial_balance,
        trading_mode=request.trading_mode,
        risk_level=request.risk_level,
        max_position_size=request.max_position_size,
        max_open_positions=request.max_open_positions,
        stop_loss_percent=request.stop_loss_percent,
        take_profit_percent=request.take_profit_percent,
        is_active=True,
        is_default=getattr(request, 'is_default', False),
    )

    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)

    return ApiResponse(
        success=True,
        data=PortfolioResponse.model_validate(portfolio),
        message="Portfolio created successfully",
    )


@router.get(
    "",
    response_model=ApiResponse[PortfolioListResponse],
)
async def list_portfolios(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's portfolios."""
    # Build query
    query = select(Portfolio).where(Portfolio.user_id == current_user.id)

    if not include_inactive:
        query = query.where(Portfolio.is_active == True)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    portfolios = result.scalars().all()

    # Convert to summary responses
    items = [
        PortfolioSummaryResponse(
            id=p.id,
            name=p.name,
            trading_mode=p.trading_mode,
            is_active=p.is_active,
            current_balance=p.current_balance,
            total_pnl=p.total_pnl,
            total_pnl_percent=p.total_pnl_percent,
            total_trades=p.total_trades,
            created_at=p.created_at,
        )
        for p in portfolios
    ]

    return ApiResponse(
        success=True,
        data=PortfolioListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{portfolio_id}",
    response_model=ApiResponse[PortfolioResponse],
)
async def get_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific portfolio by ID."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    return ApiResponse(
        success=True,
        data=PortfolioResponse.model_validate(portfolio),
    )


@router.put(
    "/{portfolio_id}",
    response_model=ApiResponse[PortfolioResponse],
)
async def update_portfolio(
    portfolio_id: UUID,
    request: PortfolioUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # Update fields
    update_data = request.model_dump(exclude_unset=True)

    # Handle default portfolio logic
    if update_data.get("is_default") and not portfolio.is_default:
        # Unset default on all other portfolios
        await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.is_default == True
            )
        )
        other_portfolios = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.is_default == True
            )
        )
        for p in other_portfolios.scalars().all():
            p.is_default = False

    for field, value in update_data.items():
        setattr(portfolio, field, value)

    await db.commit()
    await db.refresh(portfolio)

    return ApiResponse(
        success=True,
        data=PortfolioResponse.model_validate(portfolio),
        message="Portfolio updated successfully",
    )


@router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a portfolio (soft delete by deactivation)."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # Check if there are open positions
    if portfolio.current_balance != portfolio.initial_balance or portfolio.total_trades > 0:
        # Soft delete - just deactivate
        portfolio.is_active = False
        await db.commit()
    else:
        # Hard delete for empty portfolios
        await db.delete(portfolio)
        await db.commit()

    return None


@router.post(
    "/{portfolio_id}/deposit",
    response_model=ApiResponse[PortfolioResponse],
)
async def deposit_funds(
    portfolio_id: UUID,
    request: PortfolioDepositRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Deposit funds into a portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # Update balances
    portfolio.current_balance += request.amount
    portfolio.total_deposited += request.amount

    await db.commit()
    await db.refresh(portfolio)

    return ApiResponse(
        success=True,
        data=PortfolioResponse.model_validate(portfolio),
        message=f"Successfully deposited {request.amount} to portfolio",
    )


@router.post(
    "/{portfolio_id}/withdraw",
    response_model=ApiResponse[PortfolioResponse],
)
async def withdraw_funds(
    portfolio_id: UUID,
    request: PortfolioWithdrawRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Withdraw funds from a portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # Check sufficient balance
    if request.amount > portfolio.current_balance:
        raise ValidationError(
            "Insufficient balance",
            field="amount",
            extra={
                "requested": str(request.amount),
                "available": str(portfolio.current_balance),
            },
        )

    # Update balances
    portfolio.current_balance -= request.amount
    portfolio.total_withdrawn += request.amount

    await db.commit()
    await db.refresh(portfolio)

    return ApiResponse(
        success=True,
        data=PortfolioResponse.model_validate(portfolio),
        message=f"Successfully withdrew {request.amount} from portfolio",
    )


@router.get(
    "/{portfolio_id}/performance",
    response_model=ApiResponse[PortfolioPerformanceResponse],
)
async def get_portfolio_performance(
    portfolio_id: UUID,
    period: str = Query("30d", regex="^(1d|7d|30d|90d|1y|all)$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get portfolio performance metrics."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {portfolio_id} not found")

    # TODO: Implement actual performance calculation
    # For now, return placeholder data
    performance = PortfolioPerformanceResponse(
        portfolio_id=portfolio.id,
        period=period,
        total_return=portfolio.total_pnl,
        total_return_percent=portfolio.total_pnl_percent,
        annualized_return=None,
        volatility=None,
        sharpe_ratio=None,
        sortino_ratio=None,
        max_drawdown=None,
        max_drawdown_percent=None,
        total_trades=portfolio.total_trades,
        winning_trades=portfolio.winning_trades,
        losing_trades=portfolio.losing_trades,
        win_rate=Decimal("0"),
        avg_profit=Decimal("0"),
        avg_loss=Decimal("0"),
        profit_factor=None,
        benchmark_return=None,
        alpha=None,
        beta=None,
        equity_curve=None,
        daily_returns=None,
        generated_at=datetime.utcnow(),
    )

    # Calculate derived metrics
    if portfolio.total_trades > 0:
        performance.win_rate = Decimal(
            str(portfolio.winning_trades)
        ) / Decimal(str(portfolio.total_trades)) * 100

    return ApiResponse(
        success=True,
        data=performance,
    )
