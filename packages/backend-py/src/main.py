"""FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.core.logger import setup_logging
from src.database import init_db, close_db
from src.routers import health, auth, users, portfolios, positions, orders, providers, wallets, strategies, signals

setup_logging("api", settings.LOG_LEVEL)

logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - database only, no background tasks."""
    logger.info("API service starting...")
    await init_db()
    logger.info("Database initialized, API ready")

    yield

    logger.info("API service shutting down...")
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
