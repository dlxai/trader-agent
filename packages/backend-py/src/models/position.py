"""Position model."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Integer, Boolean

from .base import Base, TimestampMixin, UUIDMixin


class Position(Base, TimestampMixin):
    """Position model for tracking open and closed positions."""

    __tablename__ = "positions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        index=True,
    )
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Market info
    market_id: Mapped[str] = mapped_column(String(100), index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    market_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Position details
    side: Mapped[str] = mapped_column(String(10))  # "yes" or "no"
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, closed, liquidated

    # Size and pricing
    size: Mapped[Decimal] = mapped_column(Numeric(19, 8))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(19, 8))
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(19, 8))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(19, 8))

    # P&L tracking
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    pnl_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))

    # Fees and funding
    total_fees: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    funding_paid: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    funding_received: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))

    # Risk management
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    take_profit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    liquidation_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    margin_used: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    leverage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))

    # Timing
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(nullable=True)  # JSON field
    tags: Mapped[Optional[list]] = mapped_column(nullable=True)  # JSON field
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual, api, signal, auto
    signal_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")
    strategy: Mapped[Optional["Strategy"]] = relationship(back_populates="positions")
    orders: Mapped[List["Order"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Position(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L based on current price."""
        if self.side == "yes":
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:  # no
            self.unrealized_pnl = (self.entry_price - current_price) * self.size
        return self.unrealized_pnl

    def close_position(self, exit_price: Decimal, exit_time: datetime) -> None:
        """Close the position and calculate final P&L."""
        self.exit_price = exit_price
        self.closed_at = exit_time
        self.status = "closed"

        # Calculate realized P&L
        if self.side == "yes":
            self.realized_pnl = (exit_price - self.entry_price) * self.size
        else:
            self.realized_pnl = (self.entry_price - exit_price) * self.size

        self.total_pnl = self.realized_pnl + self.unrealized_pnl

        # Calculate percentage
        if self.entry_price > 0:
            self.pnl_percent = (self.total_pnl / (self.entry_price * self.size)) * 100
