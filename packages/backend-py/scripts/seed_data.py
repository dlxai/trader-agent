#!/usr/bin/env python3
"""Seed database with initial data."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.database import AsyncSessionLocal, init_db, close_db
from src.models.user import User
from src.core.security import get_password_hash


async def seed_users():
    """Create default users."""
    async with AsyncSessionLocal() as session:
        # Check if admin exists
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                email="admin@example.com",
                username="admin",
                hashed_password=get_password_hash("admin123"),
                is_superuser=True,
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            print("✓ Admin user created (admin/admin123)")
        else:
            print("✓ Admin user already exists")


async def main():
    """Seed database."""
    print("Seeding database...")

    try:
        await init_db()
        await seed_users()
        print("✓ Database seeded successfully")
    except Exception as e:
        print(f"✗ Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
