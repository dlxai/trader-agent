"""User routes."""

import json
import os
import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.database import get_async_session
from src.models.user import User
from src.schemas.user import UserResponse, UserUpdate, UserPreferences, UserPreferencesUpdate, AIModelConfig
from src.schemas.base import ApiResponse
from src.dependencies import get_current_user, get_current_active_user

_PROXY_URL = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None

router = APIRouter(prefix="/api/users", tags=["users"])


# Telegram config schemas
class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str


class TelegramConfigResponse(BaseModel):
    is_configured: bool
    bot_token_masked: str | None = None
    chat_id: str | None = None


def mask_token(token: str) -> str:
    """Mask bot token for display."""
    if len(token) > 8:
        return token[:6] + "***" + token[-4:]
    return "***"


async def send_telegram_message(bot_token: str, chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(proxy=_PROXY_URL) as client:
        try:
            response = await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            })
            return response.status_code == 200
        except Exception:
            return False


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
    # Try to load stored preferences from user model
    prefs = UserPreferences()

    if current_user.preferences:
        try:
            stored = json.loads(current_user.preferences)
            if "ai_models" in stored:
                prefs.ai_models = [AIModelConfig(**m) for m in stored["ai_models"]]
            if "theme" in stored:
                prefs.theme = stored["theme"]
            if "language" in stored:
                prefs.language = stored["language"]
            if "timezone" in stored:
                prefs.timezone = stored["timezone"]
            if "notifications_enabled" in stored:
                prefs.notifications_enabled = stored["notifications_enabled"]
            if "email_notifications" in stored:
                prefs.email_notifications = stored["email_notifications"]
            if "trading_notifications" in stored:
                prefs.trading_notifications = stored["trading_notifications"]
        except Exception as e:
            print(f"Error loading preferences: {e}")

    return ApiResponse(
        success=True,
        data=prefs,
    )


@router.put(
    "/me/preferences",
    response_model=ApiResponse[UserPreferences],
)
async def update_user_preferences(
    request: UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update user preferences."""
    # Load current stored preferences
    current_prefs = UserPreferences()

    if current_user.preferences:
        try:
            stored = json.loads(current_user.preferences)
            if "ai_models" in stored:
                current_prefs.ai_models = [AIModelConfig(**m) for m in stored["ai_models"]]
            if "theme" in stored:
                current_prefs.theme = stored["theme"]
            if "language" in stored:
                current_prefs.language = stored["language"]
            if "timezone" in stored:
                current_prefs.timezone = stored["timezone"]
            if "notifications_enabled" in stored:
                current_prefs.notifications_enabled = stored["notifications_enabled"]
            if "email_notifications" in stored:
                current_prefs.email_notifications = stored["email_notifications"]
            if "trading_notifications" in stored:
                current_prefs.trading_notifications = stored["trading_notifications"]
        except Exception:
            pass

    # Update with new values
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

    # Handle AI models update
    if request.ai_models is not None:
        current_prefs.ai_models = request.ai_models

    # Save to database
    current_user.preferences = json.dumps({
        "ai_models": [model.model_dump() for model in current_prefs.ai_models],
        "theme": current_prefs.theme,
        "language": current_prefs.language,
        "timezone": current_prefs.timezone,
        "notifications_enabled": current_prefs.notifications_enabled,
        "email_notifications": current_prefs.email_notifications,
        "trading_notifications": current_prefs.trading_notifications,
    })

    await db.commit()

    return ApiResponse(
        success=True,
        data=current_prefs,
        message="Preferences updated successfully",
    )


# Telegram 配置接口
@router.get(
    "/me/telegram",
    response_model=ApiResponse[TelegramConfigResponse],
)
async def get_telegram_config(
    current_user: User = Depends(get_current_active_user),
):
    """获取 Telegram 通知配置"""
    return ApiResponse(
        success=True,
        data=TelegramConfigResponse(
            is_configured=bool(current_user.telegram_bot_token and current_user.telegram_chat_id),
            bot_token_masked=mask_token(current_user.telegram_bot_token) if current_user.telegram_bot_token else None,
            chat_id=current_user.telegram_chat_id,
        ),
    )


@router.post(
    "/me/telegram",
    response_model=ApiResponse[TelegramConfigResponse],
)
async def configure_telegram(
    config: TelegramConfig,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """配置 Telegram 通知"""
    # 验证 token 是否有效 - 尝试获取 bot info
    async with httpx.AsyncClient(proxy=_PROXY_URL) as client:
        try:
            response = await client.get(f"https://api.telegram.org/bot{config.bot_token}/getMe")
            if response.status_code != 200:
                return ApiResponse(
                    success=False,
                    data=TelegramConfigResponse(is_configured=False),
                    message="Invalid bot token",
                )
        except Exception:
            return ApiResponse(
                success=False,
                data=TelegramConfigResponse(is_configured=False),
                message="Cannot connect to Telegram",
            )

    # 保存配置
    current_user.telegram_bot_token = config.bot_token
    current_user.telegram_chat_id = config.chat_id
    await db.commit()

    # 发送测试消息
    test_msg = "🎉 WestGardeng 通知配置成功！你将收到交易通知。"
    await send_telegram_message(config.bot_token, config.chat_id, test_msg)

    return ApiResponse(
        success=True,
        data=TelegramConfigResponse(
            is_configured=True,
            bot_token_masked=mask_token(config.bot_token),
            chat_id=config.chat_id,
        ),
        message="Telegram configured successfully",
    )


@router.delete(
    "/me/telegram",
    response_model=ApiResponse[dict],
)
async def delete_telegram_config(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """删除 Telegram 通知配置"""
    current_user.telegram_bot_token = None
    current_user.telegram_chat_id = None
    await db.commit()

    return ApiResponse(
        success=True,
        data={},
        message="Telegram config removed",
    )
