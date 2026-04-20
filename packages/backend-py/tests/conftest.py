"""pytest configuration and fixtures."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    """Specify async backend."""
    return "asyncio"


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client):
    """Get authentication headers."""
    # TODO: Implement login and return headers
    return {}
