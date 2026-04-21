"""Wallet schemas for Polymarket wallet configuration."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, ConfigDict

from .base import BaseSchema, PaginatedResponse


class WalletBase(BaseSchema):
    """Base wallet schema."""

    name: str = Field(..., min_length=1, max_length=100)
    proxy_url: Optional[str] = Field(None, description="Proxy URL (e.g., http://127.0.0.1:7890)")
    proxy_wallet_address: Optional[str] = Field(None, description="Proxy wallet address (Polymarket proxy wallet address)")


class WalletCreate(WalletBase):
    """Wallet creation schema."""

    private_key: str = Field(..., description="Polymarket wallet private key (0x...)")
    is_default: bool = Field(default=False, description="Set as default wallet")


class WalletUpdate(BaseSchema):
    """Wallet update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    private_key: Optional[str] = Field(None, description="New private key to replace existing")
    proxy_url: Optional[str] = None
    proxy_wallet_address: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class WalletResponse(WalletBase):
    """Wallet response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    address: Optional[str] = None
    is_active: bool
    is_default: bool
    status: str
    last_used_at: Optional[str] = None
    last_error: Optional[str] = None
    error_count: int
    usdc_balance: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WalletDetailResponse(WalletResponse):
    """Wallet detail response with balance (not returned in list)."""

    pass


class WalletTestResponse(BaseSchema):
    """Wallet test response."""

    success: bool
    message: str
    address: Optional[str] = None
    balance: Optional[str] = None
    error: Optional[str] = None


class WalletListResponse(PaginatedResponse[WalletResponse]):
    """Paginated wallet list response."""
    pass