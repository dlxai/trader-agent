"""Authentication routes."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.user import User, RefreshToken
from src.schemas.auth import (
    UserLoginRequest,
    UserRegisterRequest,
    TokenResponse,
    TokenRefreshRequest,
)
from src.schemas.user import UserResponse
from src.schemas.base import ApiResponse
from src.dependencies import get_current_user
from src.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.core.exceptions import AuthenticationError, ConflictError
from src.config import settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Register a new user. Only the first user can register."""
    # Check if any user already exists (only first user can register)
    result = await db.execute(select(User))
    existing_users = result.scalars().all()

    if existing_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Only the first user can register.",
        )

    # Check if email or username already exists
    result = await db.execute(
        select(User).where(
            or_(
                User.email == request.email,
                User.username == request.username,
            )
        )
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.email == request.email:
            raise ConflictError("Email already registered")
        else:
            raise ConflictError("Username already taken")

    # Create new user
    user = User(
        email=request.email,
        username=request.username,
        hashed_password=get_password_hash(request.password),
        is_active=True,
        is_verified=False,
        is_superuser=False,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create tokens for the new user
    access_token = create_access_token(user.id)
    refresh_token, refresh_token_id = create_refresh_token(user.id)

    # Store refresh token in database
    expires_at = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token_record = RefreshToken(
        id=refresh_token_id,
        token=refresh_token,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    await db.commit()

    # Calculate expiry
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    expires_at = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            expires_at=expires_at,
        ),
        message="User registered successfully",
    )


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
)
async def login(
    request: UserLoginRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Authenticate user and return tokens."""
    # Find user by username or email
    result = await db.execute(
        select(User).where(
            or_(
                User.username == request.username,
                User.email == request.username,
            )
        )
    )
    user = result.scalar_one_or_none()

    # Check credentials
    if user is None or not verify_password(request.password, user.hashed_password):
        raise AuthenticationError("Invalid username or password")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    # Create tokens
    access_token = create_access_token(user.id)
    refresh_token, refresh_token_id = create_refresh_token(user.id)

    # Store refresh token in database
    expires_at = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token_record = RefreshToken(
        id=refresh_token_id,
        token=refresh_token,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    await db.commit()

    # Calculate expiry
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    expires_at = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            expires_at=expires_at,
        ),
        message="Login successful",
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
)
async def refresh_token(
    request: TokenRefreshRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Refresh access token using refresh token."""
    # Decode refresh token
    payload = decode_token(request.refresh_token)
    if payload is None:
        raise AuthenticationError("Invalid or expired refresh token")

    # Verify token type
    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type")

    # Get user ID and token ID
    user_id_str = payload.get("sub")
    token_id_str = payload.get("jti")

    if not user_id_str or not token_id_str:
        raise AuthenticationError("Invalid token payload")

    try:
        user_id = UUID(user_id_str)
        token_id = UUID(token_id_str)
    except ValueError:
        raise AuthenticationError("Invalid token identifiers")

    # Check if refresh token exists in database and is not revoked
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.id == token_id,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
    )
    refresh_token_record = result.scalar_one_or_none()

    if refresh_token_record is None:
        raise AuthenticationError("Invalid refresh token")

    if refresh_token_record.is_expired():
        raise AuthenticationError("Refresh token expired")

    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    # Revoke old refresh token
    refresh_token_record.is_revoked = True

    # Create new tokens
    access_token = create_access_token(user.id)
    new_refresh_token, new_refresh_token_id = create_refresh_token(user.id)

    # Store new refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    new_refresh_record = RefreshToken(
        id=new_refresh_token_id,
        token=new_refresh_token,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(new_refresh_record)
    await db.commit()

    # Calculate expiry
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    expires_at = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            expires_at=expires_at,
        ),
        message="Token refreshed successfully",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: TokenRefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Logout user by revoking refresh token."""
    # Decode refresh token to get token ID
    payload = decode_token(request.refresh_token, verify_exp=False)
    if payload:
        token_id_str = payload.get("jti")
        if token_id_str:
            try:
                token_id = UUID(token_id_str)
                # Revoke token
                result = await db.execute(
                    select(RefreshToken).where(
                        RefreshToken.id == token_id,
                        RefreshToken.user_id == current_user.id,
                    )
                )
                token_record = result.scalar_one_or_none()
                if token_record:
                    token_record.is_revoked = True
                    await db.commit()
            except ValueError:
                pass

    return None
