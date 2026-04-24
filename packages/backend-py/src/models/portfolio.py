"""Portfolio model."""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, Integer

from src.database import Base
from .base import TimestampMixin, UUIDMixin
from .signal_log import SignalLog


class Portfolio(Base, TimestampMixin):
    """Portfolio model for tracking investments."""

    __tablename__ = "portfolios"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Balance tracking
    initial_balance: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )
    total_deposited: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )
    total_withdrawn: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )

    # Performance tracking
    total_pnl: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )
    total_pnl_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
    )
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)

    # Settings
    is_active: Mapped[bool] = mapped_column(default=True)
    is_paused: Mapped[bool] = mapped_column(default=False)
    is_default: Mapped[bool] = mapped_column(default=False)
    trading_mode: Mapped[str] = mapped_column(String(10), default="paper")
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")
    max_position_size: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8), nullable=True
    )
    max_open_positions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stop_loss_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    take_profit_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="portfolios")
    positions: Mapped[List["Position"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    orders: Mapped[List["Order"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    signals: Mapped[List["SignalLog"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    strategies: Mapped[List["Strategy"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Portfolio(id={self.id}, name={self.name}, user_id={self.user_id})>"

    def update_performance(self) -> None:
        """Recalculate portfolio performance metrics."""
        if self.initial_balance > 0:
            self.total_pnl = self.current_balance - self.initial_balance
            self.total_pnl_percent = (self.total_pnl / self.initial_balance) * 100

        total = self.winning_trades + self.losing_trades
        if total > 0:
            self.total_trades = total
