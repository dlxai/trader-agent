"""Provider model for AI model providers."""

from datetime import datetime
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, JSON

from src.database import Base
from .base import TimestampMixin


class Provider(Base, TimestampMixin):
    """Provider model for AI model providers (LLMs)."""

    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Provider info
    name: Mapped[str] = mapped_column(String(100))
    provider_type: Mapped[str] = mapped_column(String(50))  # openai, claude, deepseek, etc.

    # Provider category
    type: Mapped[str] = mapped_column(String(20), default="llm")  # llm, vision, embedding, tts

    # Credentials
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_base: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Custom endpoint
    api_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # For Azure OpenAI

    # Model configuration
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="inactive")  # active, inactive, error

    # Connection info
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(default=0)

    # Usage stats
    total_requests: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)

    # Metadata
    provider_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON

    # Relationships
    user: Mapped["User"] = relationship(back_populates="providers")

    def __repr__(self) -> str:
        return f"<Provider(id={self.id}, name={self.name}, type={self.provider_type})>"


# Add relationship to User model
from .user import User
User.providers = relationship(
    "Provider",
    back_populates="user",
    cascade="all, delete-orphan",
)