"""Test database directly."""
import asyncio
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models.user import User

async def test():
    async with AsyncSessionLocal() as db:
        # Check users
        result = await db.execute(select(User))
        users = result.scalars().all()
        print(f"Found {len(users)} users")

        # Create user
        from src.core.security import get_password_hash
        user = User(
            email="admin@test.com",
            username="admin",
            hashed_password=get_password_hash("TestPass123"),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created user: {user.username}")

if __name__ == "__main__":
    asyncio.run(test())