"""User routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.user import User
from src.schemas.user import UserResponse, UserUpdate, UserPreferences, UserPreferencesUpdate
from src.schemas.base import ApiResponse
from src.dependencies import get_current_user, get_current_active_user

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    """Get current user information."""
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user),
    )


@router.put(
    "/me",
    response_model=ApiResponse[UserResponse],
)
async def update_current_user(
    request: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update current user information."""
    # Check if email is being changed and is already taken
    if request.email and request.email != current_user.email:
        result = await db.execute(
            select(User).where(
                User.email == request.email,
                User.id != current_user.id,
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Email already registered")
        current_user.email = request.email

    # Check if username is being changed
    if request.username and request.username != current_user.username:
        result = await db.execute(
            select(User).where(
                User.username == request.username,
                User.id != current_user.id,
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Username already taken")
        current_user.username = request.username

    await db.commit()
    await db.refresh(current_user)

    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user),
        message="User updated successfully",
    )


# Need to import ConflictError
from src.core.exceptions import ConflictError


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_current_user(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete current user account (soft delete by deactivation)."""
    # Soft delete - deactivate account instead of hard delete
    current_user.is_active = False
    await db.commit()

    return None


@router.get(
    "/me/preferences",
    response_model=ApiResponse[UserPreferences],
)
async def get_user_preferences(
    current_user: User = Depends(get_current_active_user),
):
    """Get user preferences."""
    # For now, return default preferences
    # In the future, this should be stored in the database
    return ApiResponse(
        success=True,
        data=UserPreferences(),
    )


@router.put(
    "/me/preferences",
    response_model=ApiResponse[UserPreferences],
)
async def update_user_preferences(
    request: UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
):
    """Update user preferences."""
    # For now, just return the updated preferences
    # In the future, this should be stored in the database
    current_prefs = UserPreferences()

    if request.theme is not None:
        current_prefs.theme = request.theme
    if request.language is not None:
        current_prefs.language = request.language
    if request.timezone is not None:
        current_prefs.timezone = request.timezone
    if request.notifications_enabled is not None:
        current_prefs.notifications_enabled = request.notifications_enabled
    if request.email_notifications is not None:
        current_prefs.email_notifications = request.email_notifications
    if request.trading_notifications is not None:
        current_prefs.trading_notifications = request.trading_notifications

    return ApiResponse(
        success=True,
        data=current_prefs,
        message="Preferences updated successfully",
    )
