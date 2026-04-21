"""Test registration directly."""
import asyncio
from sqlalchemy import select
from src.database import async_session
from src.models.user import User
from src.core.security import get_password_hash
from src.schemas.user import UserResponse

async def test_register():
    async with async_session() as db:
        # Check if user exists
        result = await db.execute(select(User))
        existing_users = result.scalars().all()
        print(f"Existing users: {len(existing_users)}")

        # Create new user
        user = User(
            email="admin@test.com",
            username="admin",
            hashed_password=get_password_hash("TestPass123"),
            is_active=True,
            is_verified=False,
            is_superuser=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"User created: {user}")

if __name__ == "__main__":
    asyncio.run(test_register())