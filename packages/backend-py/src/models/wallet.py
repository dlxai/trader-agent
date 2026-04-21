"""Wallet model for Polymarket wallet configuration."""

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, ForeignKey, Text

from src.database import Base
from .base import TimestampMixin


class Wallet(Base, TimestampMixin):
    """Wallet model for storing Polymarket wallet configuration."""

    __tablename__ = "wallets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Wallet info
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Credentials (encrypted)
    private_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Proxy configuration
    proxy_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_wallet_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="inactive")  # active, inactive, error

    # Connection info
    last_used_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(default=0)

    # Balance info (cached)
    usdc_balance: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="wallets")

    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, name={self.name}, address={self.address})>"


# Add relationship to User model
from .user import User
User.wallets = relationship(
    "Wallet",
    back_populates="user",
    cascade="all, delete-orphan",
)