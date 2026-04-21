"""User models."""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4, UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, ForeignKey

from .base import Base, TimestampMixin
from .signal_log import SignalLog


class User(Base, TimestampMixin):
    """User model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))

    # Status flags
    is_active: Mapped[bool] = mapped_column(default=True)
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_superuser: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    portfolios: Mapped[List["Portfolio"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    strategies: Mapped[List["Strategy"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    signals: Mapped[List["SignalLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"


class RefreshToken(Base, TimestampMixin):
    """Refresh token model for JWT authentication."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_revoked: Mapped[bool] = mapped_column(default=False)

    # Foreign key
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() > self.expires_at

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id})>"
