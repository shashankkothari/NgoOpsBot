"""
Integration tests for the health and readiness endpoints.

GET /health       — liveness probe
GET /health/ready — readiness probe (checks DB + Redis)

Strategy:
- Use the HTTPX async test client against the real FastAPI app.
- For readiness tests, override the DB dependency and patch ping_redis so we
  can simulate healthy / unhealthy states without real infrastructure.
- We never call a real DB or Redis in these tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_healthy_db_session() -> AsyncMock:
    """AsyncSession mock that successfully executes SELECT 1."""
    session = AsyncMock(spec=AsyncSession)
    # execute() returns a result object; for SELECT 1 we don't use the result
    session.execute = AsyncMock(return_value=MagicMock())
    return session


def _make_broken_db_session() -> AsyncMock:
    """AsyncSession mock that raises on execute — simulates DB failure."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=Exception("connection refused"))
    return session


@pytest_asyncio.fixture
async def health_client():
    """Plain HTTPX client with no auth headers (health endpoints are public)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /health — liveness probe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liveness_returns_200(health_client: AsyncClient):
    resp = await health_client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_liveness_returns_status_ok(health_client: AsyncClient):
    resp = await health_client.get("/health")
    body = resp.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_liveness_returns_version(health_client: AsyncClient):
    resp = await health_client.get("/health")
    body = resp.json()
    assert "version" in body
    assert isinstance(body["version"], str)
    assert len(body["version"]) > 0


@pytest.mark.asyncio
async def test_liveness_does_not_hit_db(health_client: AsyncClient):
    """Liveness must respond even if DB is unreachable."""
    # No DB override — the endpoint must never call get_db
    resp = await health_client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /health/ready — readiness probe: DB + Redis both healthy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_healthy_returns_200(health_client: AsyncClient):
    db_session = _make_healthy_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=True):
        resp = await health_client.get("/health/ready")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readiness_healthy_body_contains_ok_fields(health_client: AsyncClient):
    db_session = _make_healthy_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=True):
        resp = await health_client.get("/health/ready")

    body = resp.json()
    assert body.get("database") == "ok"
    assert body.get("redis") == "ok"


# ---------------------------------------------------------------------------
# /health/ready — DB unavailable → 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_db_failure_returns_503(health_client: AsyncClient):
    db_session = _make_broken_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=True):
        resp = await health_client.get("/health/ready")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_readiness_db_failure_body_shows_error(health_client: AsyncClient):
    db_session = _make_broken_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=True):
        resp = await health_client.get("/health/ready")

    # FastAPI wraps 503 detail as {"detail": {...}}
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("database") == "error"


# ---------------------------------------------------------------------------
# /health/ready — Redis unavailable → 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_redis_failure_returns_503(health_client: AsyncClient):
    db_session = _make_healthy_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=False):
        resp = await health_client.get("/health/ready")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_readiness_redis_exception_returns_503(health_client: AsyncClient):
    """ping_redis raising an exception is treated the same as returning False."""
    db_session = _make_healthy_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch(
        "app.api.v1.health.ping_redis",
        side_effect=Exception("Redis connection refused"),
    ):
        resp = await health_client.get("/health/ready")

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# /health/ready — both DB and Redis unavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_both_unavailable_returns_503(health_client: AsyncClient):
    db_session = _make_broken_db_session()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with patch("app.api.v1.health.ping_redis", return_value=False):
        resp = await health_client.get("/health/ready")

    assert resp.status_code == 503
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("database") == "error"
    assert detail.get("redis") == "error"
