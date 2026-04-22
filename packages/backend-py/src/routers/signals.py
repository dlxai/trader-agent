"""Signal log router."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.signal_log import SignalLog
from src.models.user import User
from src.schemas.base import ApiResponse, PaginatedResponse
from src.dependencies import get_current_active_user

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalSummary:
    """Signal summary for list view."""

    def __init__(self, signal: SignalLog):
        self.id = signal.id
        self.signal_id = signal.signal_id
        self.signal_type = signal.signal_type
        self.status = signal.status
        self.side = signal.side
        self.confidence = float(signal.confidence) if signal.confidence else 0
        self.size = float(signal.size) if signal.size else None
        self.market_id = signal.market_id
        self.symbol = signal.symbol
        self.ai_thinking = signal.ai_thinking
        self.ai_model = signal.ai_model
        self.ai_tokens_used = signal.ai_tokens_used
        self.ai_duration_ms = signal.ai_duration_ms
        self.signal_reason = signal.signal_reason
        self.created_at = signal.created_at.isoformat() if signal.created_at else None


@router.get("", response_model=ApiResponse[PaginatedResponse[dict]])
async def list_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    strategy_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    portfolio_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's signals."""
    query = select(SignalLog).where(SignalLog.user_id == current_user.id)

    if strategy_id:
        query = query.where(SignalLog.strategy_id == strategy_id)

    if status_filter:
        query = query.where(SignalLog.status == status_filter)

    if portfolio_id:
        query = query.where(SignalLog.portfolio_id == portfolio_id)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Order by created_at desc
    query = query.order_by(desc(SignalLog.created_at))

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    signals = result.scalars().all()

    items = [SignalSummary(s).__dict__ for s in signals]
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ApiResponse(
        success=True,
        data=PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{signal_id}", response_model=ApiResponse[dict])
async def get_signal(
    signal_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific signal."""
    result = await db.execute(
        select(SignalLog).where(
            SignalLog.id == signal_id,
            SignalLog.user_id == current_user.id,
        )
    )
    signal = result.scalar_one_or_none()

    if signal is None:
        return ApiResponse(
            success=False,
            data=None,
            message="Signal not found",
        )

    signal_dict = {
        "id": signal.id,
        "signal_id": signal.signal_id,
        "signal_type": signal.signal_type,
        "status": signal.status,
        "side": signal.side,
        "confidence": float(signal.confidence) if signal.confidence else 0,
        "size": float(signal.size) if signal.size else None,
        "market_id": signal.market_id,
        "symbol": signal.symbol,
        "ai_thinking": signal.ai_thinking,
        "ai_model": signal.ai_model,
        "ai_tokens_used": signal.ai_tokens_used,
        "ai_duration_ms": signal.ai_duration_ms,
        "signal_reason": signal.signal_reason,
        "stop_loss_price": float(signal.stop_loss_price) if signal.stop_loss_price else None,
        "take_profit_price": float(signal.take_profit_price) if signal.take_profit_price else None,
        "risk_reward_ratio": float(signal.risk_reward_ratio) if signal.risk_reward_ratio else None,
        "input_summary": signal.input_summary,
        "decision_details": signal.decision_details,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
        "updated_at": signal.updated_at.isoformat() if signal.updated_at else None,
    }

    return ApiResponse(
        success=True,
        data=signal_dict,
    )