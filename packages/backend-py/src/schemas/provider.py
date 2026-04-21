"""Provider schemas for AI model providers."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field, ConfigDict

from .base import BaseSchema, PaginatedResponse


# Available AI model providers
AVAILABLE_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "supports": ["llm", "vision", "embedding", "tts"],
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "models": ["claude-opus-4-6", "claude-sonnet-4-5", "claude-haiku-3-5"],
        "supports": ["llm", "vision"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder"],
        "supports": ["llm"],
    },
    "google": {
        "name": "Google (Gemini)",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "supports": ["llm", "vision"],
    },
    "minimax": {
        "name": "MiniMax",
        "models": ["abab6.5s-chat", "abab6.5g-chat"],
        "supports": ["llm"],
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "models": ["kimi-long上下文", "kimi-k2"],
        "supports": ["llm"],
    },
    "qwen": {
        "name": "Qwen (Alibaba)",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "supports": ["llm", "vision"],
    },
    "grok": {
        "name": "Grok (xAI)",
        "models": ["grok-2", "grok-2-vision", "grok-beta"],
        "supports": ["llm", "vision"],
    },
    "azure": {
        "name": "Azure OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
        "supports": ["llm", "vision", "embedding"],
    },
    "custom": {
        "name": "Custom API",
        "models": [],
        "supports": ["llm", "vision", "embedding", "tts"],
    },
}


class ProviderBase(BaseSchema):
    """Base provider schema."""

    name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(...)  # openai, claude, deepseek, etc.
    type: str = Field(default="llm")  # llm, vision, embedding, tts


class ProviderCreate(ProviderBase):
    """Provider creation schema."""

    api_key: Optional[str] = None
    api_base: Optional[str] = Field(None, description="Custom API endpoint")
    api_version: Optional[str] = Field(None, description="API version (for Azure)")
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, gt=0)
    is_default: Optional[bool] = False


class ProviderUpdate(BaseSchema):
    """Provider update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class ProviderResponse(ProviderBase):
    """Provider response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    api_key: Optional[str] = None  # Masked in production
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_active: bool
    is_default: bool
    status: str
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None
    error_count: int
    total_requests: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime


class ProviderTestResponse(BaseSchema):
    """Provider test response."""

    success: bool
    message: str
    latency_ms: Optional[int] = None
    model: Optional[str] = None


class ProviderListResponse(PaginatedResponse[ProviderResponse]):
    """Paginated provider list response."""
    pass