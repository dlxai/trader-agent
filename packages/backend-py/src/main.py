"""FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import init_db, close_db
from src.routers import health, auth, users, portfolios, positions, orders, providers, wallets, strategies, signals
from src.services.position_monitor import position_monitor
from src.services.strategy_runner import strategy_runner

# Configure logging to file
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await init_db()
    # 启动持仓监控（每60秒同步链上持仓并监控止损/止盈）
    try:
        await position_monitor.start()
    except Exception as e:
        logger.error("Position monitor start failed: %s", e)

    # 后端重启后自动恢复数据库里标记为 active 的策略
    try:
        from sqlalchemy import select
        from src.database import AsyncSessionLocal
        from src.models.strategy import Strategy

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.is_active == True)
            )
            active_strategies = result.scalars().all()
            for strategy in active_strategies:
                try:
                    await strategy_runner.start_strategy(strategy.id)
                    logger.info("Auto-resumed strategy: %s (%s)", strategy.id, strategy.name)
                except Exception as e:
                    logger.error("Failed to auto-resume strategy %s: %s", strategy.id, e)
    except Exception as e:
        logger.error("Strategy auto-resume failed: %s", e)

    yield
    # Shutdown
    await position_monitor.stop()
    await close_db()


def create_application() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="JMWL Trading Backend API (Python)",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(portfolios.router)
    app.include_router(positions.router)
    app.include_router(orders.router)
    app.include_router(providers.router)
    app.include_router(wallets.router)
    app.include_router(strategies.router)
    app.include_router(signals.router)

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
