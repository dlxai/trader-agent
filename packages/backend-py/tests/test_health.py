"""Tests for health endpoints."""

import pytest


@pytest.mark.anyio
async def test_health_check(client):
    """Test basic health check endpoint."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert data["data"]["service"] == "jmwl-backend-py"
    assert "version" in data["data"]


@pytest.mark.anyio
async def test_deep_health_check(client):
    """Test deep health check endpoint."""
    response = await client.get("/health/deep")

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["data"]["status"] in ["healthy", "degraded"]
    assert "database" in data["data"]
