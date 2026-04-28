"""Position routes."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx

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


async def _fetch_market_title(market_id: str) -> str:
    """Fetch market title from Gamma API when data-api doesn't provide one."""
    if not market_id or not market_id.startswith("0x"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"condition_ids": market_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("question") or data[0].get("title") or ""
    except Exception:
        pass
    return ""


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
    query = (
        select(Position)
        .join(Portfolio)
        .options(selectinload(Position.portfolio))
        .where(Portfolio.user_id == current_user.id)
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
    items = []
    for p in positions:
        portfolio_mini = None
        if p.portfolio:
            portfolio_mini = {"id": p.portfolio.id, "name": p.portfolio.name}
        items.append(
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
                market_name=(p.position_metadata or {}).get("market_name") or p.symbol,
                title=(p.position_metadata or {}).get("title") or p.symbol,
                outcome=(p.position_metadata or {}).get("outcome") or p.side,
                portfolio=portfolio_mini,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ApiResponse(
        success=True,
        data=PositionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
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


@router.post(
    "/sync",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
)
async def sync_positions_from_chain(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """从 Polymarket 链上同步持仓到本地数据库.

    使用 data-api.polymarket.com/positions 直接拉取持仓数据，
    然后写入/更新本地 positions 表。
    """
    from uuid import uuid4
    import os
    from src.models.wallet import Wallet

    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None

    # 1. 获取用户的默认钱包
    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == current_user.id,
            Wallet.is_default == True,
        )
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == current_user.id,
                Wallet.status == "active",
            ).limit(1)
        )
        wallet = result.scalar_one_or_none()

    if not wallet:
        raise NotFoundError("Wallet", "No active wallet found for user")

    # 2. 获取或创建默认 portfolio
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
        ).limit(1)
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        portfolio = Portfolio(
            id=uuid4(),
            user_id=current_user.id,
            name="Default Portfolio",
            initial_balance=Decimal("0"),
            current_balance=Decimal("0"),
            total_pnl=Decimal("0"),
            status="active",
        )
        db.add(portfolio)
        await db.flush()

    # 3. 从 data-api 拉取链上持仓
    try:
        address = wallet.proxy_wallet_address or wallet.address
        if not address:
            raise ValidationError("Wallet has no address")

        async with httpx.AsyncClient(proxy=proxy_url, timeout=15) as client:
            resp = await client.get(
                "https://data-api.polymarket.com/positions",
                params={
                    "sizeThreshold": "1",
                    "limit": "100",
                    "sortBy": "TOKENS",
                    "sortDirection": "DESC",
                    "user": address,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        positions_list = data if isinstance(data, list) else data.get("positions", [])
        if not isinstance(positions_list, list):
            raise ValidationError("Invalid response from data-api")

        # 规范化持仓数据
        onchain_list = []
        for p in positions_list:
            if not isinstance(p, dict):
                continue
            size = float(p.get("size") or p.get("quantity") or 0)
            if size <= 0:
                continue

            token_id = p.get("tokenId") or p.get("token_id") or ""
            market_id = p.get("conditionId") or p.get("marketId") or ""
            title = p.get("title") or p.get("question") or p.get("marketName") or p.get("market") or ""
            outcome = p.get("outcome") or p.get("position") or ""
            # data-api has no "side" field; derive from outcome
            side = "yes" if outcome.lower() == "yes" else "no"
            avg_price = float(p.get("avgPrice") or p.get("avgCost") or p.get("avg_cost") or 0.5)
            cur_price = float(p.get("curPrice") or 0)
            cash_pnl = float(p.get("cashPnl") or p.get("unrealizedPnl") or p.get("unrealized_pnl") or 0)
            percent_pnl = float(p.get("percentPnl") or p.get("percentPnl") or 0)

            onchain_list.append({
                "token_id": token_id,
                "market_id": market_id,
                "title": title,
                "outcome": outcome,
                "side": side,
                "size": Decimal(str(size)),
                "avg_price": avg_price,
                "cur_price": cur_price,
                "unrealized_pnl": cash_pnl,
                "pnl_percent": percent_pnl,
            })

        synced_count = 0
        closed_count = 0

        # 获取本地已有的持仓
        result = await db.execute(
            select(Position).where(Position.portfolio_id == portfolio.id)
        )
        local_positions = {str(p.market_id): p for p in result.scalars().all()}
        onchain_keys = set()

        # 更新或创建持仓
        for ocp in onchain_list:
            market_id = ocp["market_id"] or ocp["token_id"]
            onchain_keys.add(market_id)

            title = ocp["title"]
            if not title:
                title = await _fetch_market_title(market_id)
            display_name = title or ocp["outcome"] or market_id[:50]
            avg_price = Decimal(str(ocp["avg_price"]))
            size = ocp["size"]
            unrealized = Decimal(str(ocp["unrealized_pnl"]))
            # Use curPrice from data-api if available; otherwise derive
            if ocp.get("cur_price"):
                current_price = Decimal(str(ocp["cur_price"]))
            else:
                if size > 0:
                    current_price = avg_price + (unrealized / size)
                else:
                    current_price = avg_price
            # Use percentPnl from data-api if available; otherwise compute
            if ocp.get("pnl_percent"):
                pnl_percent = Decimal(str(ocp["pnl_percent"]))
            else:
                cost_basis = avg_price * size
                if cost_basis > 0:
                    pnl_percent = (unrealized / cost_basis) * Decimal("100")
                else:
                    pnl_percent = Decimal("0")

            if market_id in local_positions:
                local_pos = local_positions[market_id]
                local_pos.size = size
                local_pos.entry_price = avg_price
                local_pos.current_price = current_price
                local_pos.average_entry_price = avg_price
                local_pos.unrealized_pnl = unrealized
                local_pos.total_pnl = unrealized
                local_pos.pnl_percent = pnl_percent
                local_pos.status = "open"
                local_pos.last_updated_at = datetime.utcnow()
                if display_name:
                    local_pos.symbol = display_name
                    meta = local_pos.position_metadata or {}
                    meta["market_name"] = display_name
                    meta["title"] = title or display_name
                    meta["outcome"] = ocp.get("outcome") or local_pos.side
                    local_pos.position_metadata = meta
                synced_count += 1
            else:
                new_position = Position(
                    id=uuid4(),
                    portfolio_id=portfolio.id,
                    market_id=market_id,
                    token_id=ocp["token_id"],
                    symbol=display_name,
                    side=ocp["side"],
                    status="open",
                    size=size,
                    entry_price=avg_price,
                    current_price=current_price,
                    average_entry_price=avg_price,
                    realized_pnl=Decimal("0"),
                    unrealized_pnl=unrealized,
                    total_pnl=unrealized,
                    pnl_percent=pnl_percent,
                    opened_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow(),
                    source="chain_sync",
                    position_metadata={
                        "token_id": ocp["token_id"],
                        "chain_updated_at": str(datetime.utcnow()),
                        "market_name": display_name,
                        "title": title or display_name,
                        "outcome": ocp.get("outcome") or ocp["side"],
                    },
                )
                db.add(new_position)
                synced_count += 1

        # 关闭链上已平仓但本地还显示开的持仓
        for market_id, local_pos in local_positions.items():
            if market_id not in onchain_keys and local_pos.status == "open":
                local_pos.status = "closed"
                local_pos.closed_at = datetime.utcnow()
                closed_count += 1

        await db.commit()

        return ApiResponse(
            success=True,
            data={
                "synced": synced_count,
                "closed": closed_count,
                "total_chain_positions": len(onchain_list),
                "wallet_address": wallet.address[:10] + "...",
            },
            message=f"Synced {synced_count} positions from chain",
        )

    except Exception as e:
        await db.rollback()
        raise ValidationError(f"Failed to sync positions: {str(e)}")
