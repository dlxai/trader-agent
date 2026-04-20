"""Health check endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.schemas.base import ApiResponse, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ApiResponse[HealthResponse], status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint."""
    return ApiResponse(
        success=True,
        data=HealthResponse(
            status="healthy",
            version="0.1.0",
            service="jmwl-backend-py"
        )
    )


@router.get("/deep", response_model=ApiResponse[HealthResponse], status_code=status.HTTP_200_OK)
async def deep_health_check(session: AsyncSession = Depends(get_async_session)):
    """Deep health check including database connection."""
    try:
        # Test database connection
        result = await session.execute(text("SELECT 1"))
        await result.scalar()
        db_status = "connected"
        overall_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
        overall_status = "degraded"

    return ApiResponse(
        success=True,
        data=HealthResponse(
            status=overall_status,
            version="0.1.0",
            service="jmwl-backend-py",
            database=db_status
        )
    )
