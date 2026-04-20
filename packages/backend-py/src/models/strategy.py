"""Strategy model."""

from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, Integer, Boolean, JSON

from .base import Base, TimestampMixin, UUIDMixin


class Strategy(Base, TimestampMixin):
    """Strategy model for trading strategies."""

    __tablename__ = "strategies"

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

    # Basic info
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    # buy_strategy, capital_flow, arbitrage, market_making, etc.

    # Status
    is_active: Mapped[bool] = mapped_column(default=False)
    is_paused: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft, testing, active, paused, stopped, archived

    # Risk parameters
    max_position_size: Mapped[Decimal] = mapped_column(
        Numeric(19, 8),
        default=Decimal("0"),
    )
    max_open_positions: Mapped[int] = mapped_column(Integer, default=0)
    stop_loss_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    take_profit_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    trailing_stop_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Capital allocation
    allocation_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("100"),
    )
    max_daily_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    max_weekly_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )

    # Execution settings
    order_type: Mapped[str] = mapped_column(String(20), default="market")
    time_in_force: Mapped[str] = mapped_column(String(20), default="GTC")
    slippage_tolerance: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.001"),
    )

    # Market filters
    allowed_markets: Mapped[Optional[list]] = mapped_column(nullable=True)  # JSON list
    excluded_markets: Mapped[Optional[list]] = mapped_column(nullable=True)  # JSON list
    min_liquidity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(19, 8),
        nullable=True,
    )
    max_spread_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Time settings
    trading_schedule: Mapped[Optional[dict]] = mapped_column(nullable=True)  # JSON
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Performance tracking
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(19, 8), default=Decimal("0"))
    sharpe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    # Configuration storage
    config: Mapped[Optional[dict]] = mapped_column(nullable=True)  # JSON config
    parameters: Mapped[Optional[dict]] = mapped_column(nullable=True)  # JSON parameters
    metadata: Mapped[Optional[dict]] = mapped_column(nullable=True)  # JSON metadata

    # Version control
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_strategy_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="strategies")
    portfolio: Mapped[Optional["Portfolio"]] = relationship(back_populates="strategies")
    positions: Mapped[List["Position"]] = relationship(back_populates="strategy")
    orders: Mapped[List["Order"]] = relationship(back_populates="strategy")
    signals: Mapped[List["SignalLog"]] = relationship(back_populates="strategy")

    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name={self.name}, type={self.type}, status={self.status})>"

    def calculate_win_rate(self) -> Decimal:
        """Calculate win rate percentage."""
        total = self.winning_trades + self.losing_trades
        if total == 0:
            return Decimal("0")
        return (Decimal(str(self.winning_trades)) / Decimal(str(total))) * 100

    def update_performance(self, pnl: Decimal, is_win: bool) -> None:
        """Update strategy performance after a trade."""
        self.total_pnl += pnl
        self.total_trades += 1
        if is_win:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

    def is_within_risk_limits(self, daily_pnl: Decimal, weekly_pnl: Decimal) -> bool:
        """Check if strategy is within risk limits."""
        if self.max_daily_loss is not None and daily_pnl < -self.max_daily_loss:
            return False
        if self.max_weekly_loss is not None and weekly_pnl < -self.max_weekly_loss:
            return False
        return True
