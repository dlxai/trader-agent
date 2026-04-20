#!/usr/bin/env python3
"""Initialize database script."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.database import init_db, close_db
from src.config import settings


async def main():
    """Initialize database."""
    print(f"Initializing database...")
    print(f"Database URL: {settings.async_database_url}")

    try:
        await init_db()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
