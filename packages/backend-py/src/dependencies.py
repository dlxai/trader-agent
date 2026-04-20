"""FastAPI dependencies."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.user import User
from src.core.security import decode_token
from src.core.exceptions import AuthenticationError, AuthorizationError

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Get current authenticated user.

    Raises:
        AuthenticationError: If authentication fails.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required")

    token = credentials.credentials

    # Decode token
    payload = decode_token(token)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    # Verify token type
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    # Get user_id from token
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise AuthenticationError("Invalid token payload")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid user ID in token")

    # Fetch user from database
    from sqlalchemy import select
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is deactivated")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user.

    Additional check to ensure user is active.
    """
    if not current_user.is_active:
        raise AuthorizationError("User account is deactivated")
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current superuser.

    Requires user to have is_superuser flag.
    """
    if not current_user.is_superuser:
        raise AuthorizationError("Superuser privileges required")
    return current_user


# Type alias for dependency injection
CurrentUser = Depends(get_current_user)
CurrentActiveUser = Depends(get_current_active_user)
CurrentSuperuser = Depends(get_current_superuser)
