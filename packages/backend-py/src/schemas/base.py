"""Base Pydantic schemas."""

from typing import Any, Dict, Generic, List, Optional, TypeVar
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ApiResponse(BaseSchema, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    data: Optional[T] = None
    error: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


class HealthResponse(BaseSchema):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    service: str = "jmwl-backend-py"
    database: Optional[str] = None


class PaginationParams(BaseSchema):
    """Pagination query parameters."""

    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Paginated response wrapper."""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
