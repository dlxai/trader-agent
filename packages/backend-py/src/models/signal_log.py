"""Signal log model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON

from .base import Base, TimestampMixin, UUIDMixin


class SignalLog(Base, TimestampMixin):
    """Signal log model for tracking trading signals."""

    __tablename__ = "signal_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    portfolio_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Signal identification
    signal_id: Mapped[str] = mapped_column(String(100), index=True)
    signal_type: Mapped[str] = mapped_column(String(50), index=True)
    # buy, sell, hold, close, modify_risk, etc.

    # Signal status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, approved, rejected, executed, expired, cancelled, failed

    # Market info
    market_id: Mapped[str] = mapped_column(String(100), index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    market_condition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # trending_up, trending_down, ranging, volatile, etc.

    # Signal details
    side: Mapped[str] = mapped_column(String(10))  # yes, no, buy, sell
    size: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 8), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    # 0 to 1 confidence score

    # Pricing
    suggested_entry_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    current_market_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    expected_exit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )

    # Risk/reward
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    take_profit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    risk_reward_ratio: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    max_risk_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )

    # Time
    signal_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Execution details
    execution_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    execution_size: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    execution_fees: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    execution_slippage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # Reasoning
    signal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_indicators: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON
    fundamental_factors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON
    market_sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # AI/ML fields
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON

    # Review and feedback
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    was_profitable: Mapped[Optional[bool]] = mapped_column(nullable=True)
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Metadata
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # JSON list
    signal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON
    source: Mapped[str] = mapped_column(String(50), default="system")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="signals")
    portfolio: Mapped[Optional["Portfolio"]] = relationship(back_populates="signals")
    strategy: Mapped[Optional["Strategy"]] = relationship(back_populates="signals")
    position: Mapped[Optional["Position"]] = relationship()

    def __repr__(self) -> str:
        return f"<SignalLog(id={self.id}, signal_id={self.signal_id}, status={self.status})>"

    def is_valid(self) -> bool:
        """Check if signal is still valid (not expired)."""
        if self.status not in ["pending", "approved"]:
            return False
        if self.valid_until and datetime.utcnow() > self.valid_until:
            return False
        return True

    def calculate_potential_pnl(self, exit_price: Decimal) -> Decimal:
        """Calculate potential P&L given an exit price."""
        if self.side == "yes":
            return (exit_price - (self.suggested_entry_price or self.current_market_price or Decimal("0"))) * (self.size or Decimal("0"))
        else:
            return ((self.suggested_entry_price or self.current_market_price or Decimal("0")) - exit_price) * (self.size or Decimal("0"))

    def mark_as_executed(self, execution_price: Decimal, execution_size: Decimal, execution_fees: Decimal) -> None:
        """Mark signal as executed."""
        self.status = "executed"
        self.executed_at = datetime.utcnow()
        self.execution_price = execution_price
        self.execution_size = execution_size
        self.execution_fees = execution_fees

    def mark_as_expired(self) -> None:
        """Mark signal as expired."""
        if self.status in ["pending", "approved"]:
            self.status = "expired"
            self.expired_at = datetime.utcnow()

    def mark_as_rejected(self, reason: str) -> None:
        """Mark signal as rejected."""
        self.status = "rejected"
        self.review_notes = reason
        self.reviewed_at = datetime.utcnow()
