"""Notification service for sending alerts to users."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.user import User


async def send_telegram_notification(
    user_id: str,
    message: str,
    db: AsyncSession
) -> bool:
    """Send notification via Telegram if user has configured it."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.telegram_bot_token or not user.telegram_chat_id:
        return False

    return await _send_telegram_message(
        user.telegram_bot_token,
        user.telegram_chat_id,
        message
    )


async def _send_telegram_message(bot_token: str, chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            })
            return response.status_code == 200
        except Exception:
            return False


# 通知模板
def format_order_notification(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    status: str
) -> str:
    """格式化订单通知消息"""
    emoji = "🟢" if side == "buy" else "🔴"
    return f"""
{emoji} 订单{status}

品种: {symbol}
方向: {'买入' if side == 'buy' else '卖出'}
数量: {quantity}
价格: ${price}
状态: {status}
"""


def format_position_notification(
    symbol: str,
    side: str,
    pnl: float,
    pnl_percent: float
) -> str:
    """格式化持仓通知消息"""
    emoji = "📈" if pnl >= 0 else "📉"
    return f"""
{emoji} 持仓更新

品种: {symbol}
方向: {'多头' if side == 'long' else '空头'}
盈亏: ${pnl:.2f} ({pnl_percent:+.2f}%)
"""