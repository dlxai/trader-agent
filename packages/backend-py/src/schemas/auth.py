"""Authentication schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from .base import BaseSchema


class TokenResponse(BaseSchema):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    expires_at: datetime


class TokenPayload(BaseModel):
    """Token payload for JWT decoding."""

    sub: Optional[str] = None  # user_id
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None
    type: Optional[str] = None  # access or refresh
    jti: Optional[str] = None  # token id


class UserLoginRequest(BaseSchema):
    """User login request."""

    username: str = Field(..., min_length=3, max_length=100, description="Username or email")
    password: str = Field(..., min_length=6, description="Password")


class UserRegisterRequest(BaseSchema):
    """User registration request."""

    email: EmailStr = Field(..., description="Email address")
    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, underscore, hyphen)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Password (min 8 characters)",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class TokenRefreshRequest(BaseSchema):
    """Token refresh request."""

    refresh_token: str = Field(..., description="Refresh token")


class PasswordChangeRequest(BaseSchema):
    """Password change request."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New password",
    )


class PasswordResetRequest(BaseSchema):
    """Password reset request."""

    email: EmailStr = Field(..., description="Email address")


class PasswordResetConfirmRequest(BaseSchema):
    """Password reset confirmation request."""

    token: str = Field(..., description="Reset token")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New password",
    )
