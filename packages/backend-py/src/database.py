"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base, DeclarativeBase
from sqlalchemy.pool import NullPool

from src.config import settings


# 使用 SQLAlchemy 2.0 DeclarativeBase
class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# Create async engine
engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    poolclass=NullPool if settings.DATABASE_TYPE == "sqlite" else None,
    future=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Import all models to register them with Base.metadata
from src.models import User, Portfolio, Position, Order, Strategy, Wallet, Provider  # noqa: F401, E402


async def get_async_session() -> AsyncSession:
    """Async session generator for dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database (create all tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await engine.dispose()
