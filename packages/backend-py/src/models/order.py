"""Order model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Integer, JSON, UniqueConstraint

from src.database import Base
from .base import TimestampMixin, UUIDMixin


class Order(Base, TimestampMixin):
    """Order model for tracking trade orders."""

    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_order_signal_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        index=True,
    )
    position_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
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

    # Order details
    side: Mapped[str] = mapped_column(String(10))  # "yes" or "no"
    order_type: Mapped[str] = mapped_column(String(20))  # market, limit, stop, stop_limit
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, open, partially_filled, filled, cancelled, rejected, expired

    # Size and pricing
    size: Mapped[Decimal] = mapped_column(Numeric(19, 8))
    filled_size: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    remaining_size: Mapped[Decimal] = mapped_column(Numeric(19, 8))

    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)

    # Cost and fees
    total_cost: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    fee_currency: Mapped[str] = mapped_column(String(10), default="USDC")

    # Time in force
    time_in_force: Mapped[str] = mapped_column(String(20), default="GTC")
    # GTC (Good Till Cancelled), IOC (Immediate Or Cancel), FOK (Fill Or Kill)

    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Execution details
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reject_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # External IDs
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Slippage
    expected_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    slippage_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))

    # Metadata
    order_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON field
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual, api, signal, auto
    signal_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(back_populates="orders")
    position: Mapped[Optional["Position"]] = relationship(back_populates="orders")
    strategy: Mapped[Optional["Strategy"]] = relationship(back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"

    def calculate_fees(self, fee_rate: Decimal) -> Decimal:
        """Calculate fees for this order."""
        if self.avg_fill_price and self.filled_size > 0:
            fill_value = self.avg_fill_price * self.filled_size
            self.total_fees = fill_value * fee_rate
            return self.total_fees
        return Decimal("0")

    def update_fill(self, filled_size: Decimal, avg_fill_price: Decimal) -> None:
        """Update order with fill information."""
        self.filled_size = filled_size
        self.remaining_size = self.size - filled_size
        self.avg_fill_price = avg_fill_price
        self.total_cost = filled_size * avg_fill_price

        if self.remaining_size <= 0:
            self.status = "filled"
            self.executed_at = datetime.utcnow()
        elif self.filled_size > 0:
            self.status = "partially_filled"

    def cancel(self) -> None:
        """Cancel the order."""
        if self.status in ["pending", "open", "partially_filled"]:
            self.status = "cancelled"
            self.cancelled_at = datetime.utcnow()

    def reject(self, reason: str, code: Optional[str] = None) -> None:
        """Reject the order."""
        self.status = "rejected"
        self.reject_reason = reason
        self.reject_code = code
