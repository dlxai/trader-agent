"""User schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import EmailStr, Field, ConfigDict

from .base import BaseSchema, PaginatedResponse


class UserBase(BaseSchema):
    """Base user schema."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    is_active: bool = True
    is_verified: bool = False


class UserCreate(UserBase):
    """User creation schema."""

    password: str = Field(..., min_length=8)


class UserUpdate(BaseSchema):
    """User update schema."""

    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class UserProfileResponse(UserResponse):
    """Extended user profile response."""

    portfolio_count: int = 0
    total_positions: int = 0


class UserListResponse(PaginatedResponse[UserResponse]):
    """Paginated user list response."""
    pass


class UserPreferences(BaseSchema):
    """User preferences schema."""

    theme: str = "dark"  # dark, light, system
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    notifications_enabled: bool = True
    email_notifications: bool = True
    trading_notifications: bool = True


class UserPreferencesUpdate(BaseSchema):
    """User preferences update schema."""

    theme: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    trading_notifications: Optional[bool] = None
