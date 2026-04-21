"""Initialize database tables."""
import asyncio
from src.database import engine
from src.models.base import Base
from src.models.user import User
from src.models.portfolio import Portfolio
from src.models.strategy import Strategy
from src.models.position import Position
from src.models.order import Order
from src.models.signal_log import SignalLog

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(init())