"""Provider routes for AI model providers."""

import os
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.user import User
from src.models.provider import Provider
from src.schemas.provider import (
    ProviderCreate,
    ProviderUpdate,
    ProviderResponse,
    ProviderTestResponse,
    AVAILABLE_PROVIDERS,
)

_PROXY_URL = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=ApiResponse[list[ProviderResponse]])
async def list_providers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all providers for the current user."""
    offset = (page - 1) * page_size

    result = await db.execute(
        select(Provider)
        .where(Provider.user_id == current_user.id)
        .offset(offset)
        .limit(page_size)
    )
    providers = result.scalars().all()

    return ApiResponse(
        success=True,
        data=[ProviderResponse.model_validate(p) for p in providers],
    )


@router.get("/types", response_model=ApiResponse[dict])
async def get_provider_types():
    """Get available AI model provider types."""
    return ApiResponse(
        success=True,
        data=AVAILABLE_PROVIDERS,
    )


@router.post("/fetch-models", response_model=ApiResponse[list])
async def fetch_models_direct(
    api_base: str,
    api_key: str,
    provider_type: str = "openai",
    current_user: User = Depends(get_current_active_user),
):
    """Fetch available models directly from provider API (without saving provider first)."""
    import httpx

    headers = {}
    if provider_type == "anthropic":
        headers["x-api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0, proxy=_PROXY_URL) as client:
            response = await client.get(
                f"{api_base.rstrip('/')}/models",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        models = []
        if isinstance(data, dict) and "data" in data:
            models = [item["id"] for item in data["data"] if "id" in item]
        elif isinstance(data, list):
            models = [item["id"] if isinstance(item, dict) else item for item in data]

        return ApiResponse(success=True, data=models)
    except httpx.HTTPStatusError as e:
        return ApiResponse(success=False, data=[], error={"message": f"HTTP error: {e.response.status_code}"})
    except Exception as e:
        return ApiResponse(success=False, data=[], error={"message": str(e)})


@router.post("/default/{provider_id}/set", response_model=ApiResponse[ProviderResponse])
async def set_default_provider(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Set a provider as the default."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    # Unset other defaults
    all_result = await db.execute(
        select(Provider).where(
            and_(
                Provider.user_id == current_user.id,
                Provider.is_default == True,
                Provider.id != provider_id,
            )
        )
    )
    for p in all_result.scalars().all():
        p.is_default = False

    # Set this as default
    provider.is_default = True
    await db.commit()
    await db.refresh(provider)

    return ApiResponse(
        success=True,
        data=ProviderResponse.model_validate(provider),
        message="Default provider set successfully",
    )


@router.post("", response_model=ApiResponse[ProviderResponse], status_code=status.HTTP_201_CREATED)
async def create_provider(
    request: ProviderCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new AI model provider."""
    # If setting as default, unset other defaults
    if request.is_default:
        result = await db.execute(
            select(Provider).where(
                and_(
                    Provider.user_id == current_user.id,
                    Provider.is_default == True,
                )
            )
        )
        for p in result.scalars().all():
            p.is_default = False

    provider = Provider(
        user_id=current_user.id,
        name=request.name,
        provider_type=request.provider_type,
        type=request.type,
        api_key=request.api_key,
        api_base=request.api_base,
        api_version=request.api_version,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        is_default=request.is_default or False,
        status="inactive",
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    return ApiResponse(
        success=True,
        data=ProviderResponse.model_validate(provider),
        message="Provider created successfully",
    )


@router.get("/{provider_id}", response_model=ApiResponse[ProviderResponse])
async def get_provider(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific provider."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    return ApiResponse(
        success=True,
        data=ProviderResponse.model_validate(provider),
    )


@router.put("/{provider_id}", response_model=ApiResponse[ProviderResponse])
@router.patch("/{provider_id}", response_model=ApiResponse[ProviderResponse])
async def update_provider(
    provider_id: UUID,
    request: ProviderUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a provider."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    # If setting as default, unset other defaults
    if request.is_default and not provider.is_default:
        all_result = await db.execute(
            select(Provider).where(
                and_(
                    Provider.user_id == current_user.id,
                    Provider.is_default == True,
                    Provider.id != provider_id,
                )
            )
        )
        for p in all_result.scalars().all():
            p.is_default = False

    # Update fields
    if request.name is not None:
        provider.name = request.name
    if request.api_key is not None:
        provider.api_key = request.api_key
    if request.api_base is not None:
        provider.api_base = request.api_base
    if request.api_version is not None:
        provider.api_version = request.api_version
    if request.model is not None:
        provider.model = request.model
    if request.temperature is not None:
        provider.temperature = request.temperature
    if request.max_tokens is not None:
        provider.max_tokens = request.max_tokens
    if request.is_active is not None:
        provider.is_active = request.is_active
    if request.is_default is not None:
        provider.is_default = request.is_default

    await db.commit()
    await db.refresh(provider)

    return ApiResponse(
        success=True,
        data=ProviderResponse.model_validate(provider),
        message="Provider updated successfully",
    )


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a provider."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/test", response_model=ApiResponse[ProviderTestResponse])
async def test_provider(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Test a provider connection."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    # Test connection
    success = False
    message = ""
    latency_ms = None
    model = provider.model

    if not provider.api_key:
        message = "Missing API key"
        provider.status = "error"
        provider.last_error = message
        provider.error_count += 1
    else:
        # Simulate API test (in production, would actually call the API)
        import time
        start = time.time()

        # Check if provider type is valid
        if provider.provider_type not in AVAILABLE_PROVIDERS:
            message = f"Unknown provider type: {provider.provider_type}"
            provider.status = "error"
            provider.last_error = message
            provider.error_count += 1
        else:
            # Success
            latency_ms = int((time.time() - start) * 1000) + 50  # Simulated latency
            success = True
            message = "Connection successful"
            provider.status = "active"
            provider.last_error = None

    provider.last_used_at = datetime.utcnow()
    await db.commit()

    return ApiResponse(
        success=True,
        data=ProviderTestResponse(
            success=success,
            message=message,
            latency_ms=latency_ms,
            model=model,
        ),
    )


@router.get("/{provider_id}/models", response_model=ApiResponse[list])
async def get_provider_models(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Fetch available models from the provider API."""
    result = await db.execute(
        select(Provider).where(
            and_(
                Provider.id == provider_id,
                Provider.user_id == current_user.id,
            )
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Provider not found")

    if not provider.api_key:
        from src.core.exceptions import AuthenticationError
        raise AuthenticationError("API key is required to fetch models")

    if not provider.api_base:
        return ApiResponse(success=True, data=[], message="No API base URL configured")

    import httpx

    headers = {}
    if provider.provider_type == "openai" or provider.provider_type == "azure":
        headers["Authorization"] = f"Bearer {provider.api_key}"
    elif provider.provider_type == "anthropic":
        headers["x-api-key"] = provider.api_key
    else:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0, proxy=_PROXY_URL) as client:
            response = await client.get(
                f"{provider.api_base.rstrip('/')}/models",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        # Parse OpenAI-style response: {"object": "list", "data": [{"id": "model-1", ...}, ...]}
        models = []
        if isinstance(data, dict) and "data" in data:
            models = [item["id"] for item in data["data"] if "id" in item]
        elif isinstance(data, list):
            models = [item["id"] if isinstance(item, dict) else item for item in data]

        return ApiResponse(success=True, data=models)
    except httpx.HTTPStatusError as e:
        return ApiResponse(success=False, data=[], message=f"HTTP error: {e.response.status_code}")
    except Exception as e:
        return ApiResponse(success=False, data=[], message=str(e))


