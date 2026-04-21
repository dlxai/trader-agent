"""Strategy router."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.user import User
from src.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategySummary,
    StrategyListResponse,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.exceptions import NotFoundError

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.post(
    "",
    response_model=ApiResponse[StrategyResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy(
    request: StrategyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new strategy."""
    # 验证 portfolio 存在
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == request.portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {request.portfolio_id} not found")

    # 创建策略
    strategy = Strategy(
        id=UUID(),
        user_id=current_user.id,
        portfolio_id=request.portfolio_id,
        name=request.name,
        description=request.description,
        type="ai_trading",
        provider_id=request.provider_id,
        system_prompt=request.system_prompt,
        custom_prompt=request.custom_prompt,
        data_sources=request.data_sources or {},
        min_order_size=request.min_order_size,
        max_order_size=request.max_order_size,
        market_filter_days=request.market_filter_days,
        market_filter_type=request.market_filter_type,
        run_interval_minutes=request.run_interval_minutes,
        max_position_size=request.max_position_size or portfolio.max_position_size,
        max_open_positions=request.max_open_positions or portfolio.max_open_positions,
        stop_loss_percent=request.stop_loss_percent or portfolio.stop_loss_percent,
        take_profit_percent=request.take_profit_percent or portfolio.take_profit_percent,
        is_active=False,
        status="draft",
    )

    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy created successfully",
    )


@router.get(
    "",
    response_model=ApiResponse[StrategyListResponse],
)
async def list_strategies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    portfolio_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's strategies."""
    query = select(Strategy).where(Strategy.user_id == current_user.id)

    if portfolio_id:
        query = query.where(Strategy.portfolio_id == portfolio_id)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    strategies = result.scalars().all()

    items = [
        StrategySummary(
            id=s.id,
            name=s.name,
            type=s.type,
            is_active=s.is_active,
            status=s.status,
            min_order_size=s.min_order_size,
            max_order_size=s.max_order_size,
            total_trades=s.total_trades,
            total_pnl=s.total_pnl,
        )
        for s in strategies
    ]

    return ApiResponse(
        success=True,
        data=StrategyListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{strategy_id}",
    response_model=ApiResponse[StrategyResponse],
)
async def get_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
    )


@router.put(
    "/{strategy_id}",
    response_model=ApiResponse[StrategyResponse],
)
async def update_strategy(
    strategy_id: UUID,
    request: StrategyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    update_data = request.model_dump(exclude_unset=True)

    # 处理 is_active 状态变更
    if "is_active" in update_data:
        new_active = update_data.pop("is_active")
        if new_active and not strategy.is_active:
            strategy.status = "active"
        elif not new_active and strategy.is_active:
            strategy.status = "stopped"

    for field, value in update_data.items():
        setattr(strategy, field, value)

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy updated successfully",
    )


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    strategy.is_active = False
    strategy.status = "archived"

    await db.commit()

    return None


@router.post(
    "/{strategy_id}/start",
    response_model=ApiResponse[StrategyResponse],
)
async def start_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Start a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    strategy.is_active = True
    strategy.status = "active"

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy started successfully",
    )


@router.post(
    "/{strategy_id}/stop",
    response_model=ApiResponse[StrategyResponse],
)
async def stop_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Stop a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    strategy.is_active = False
    strategy.status = "stopped"

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy stopped successfully",
    )


@router.post(
    "/{strategy_id}/run-once",
    response_model=ApiResponse[dict],
)
async def run_strategy_once(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Manually trigger strategy execution once."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    return ApiResponse(
        success=True,
        data={"message": "Strategy execution triggered"},
    )
