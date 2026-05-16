"""
Integration test fixtures.

The core challenge: HTTPX's ASGITransport fires ASGI lifespan events (startup /
shutdown) inside anyio's managed context, which creates asyncpg connections on
anyio's internal loop rather than the pytest session loop. When subsequent tests
reuse those pool connections on the session loop, asyncpg raises
"Future attached to a different loop".

Fix: patch the ASGI lifespan to a no-op so connections are never created in an
anyio context. The SQLAlchemy engine was already created at import time; asyncpg
connections are created lazily on the FIRST request — which runs on the pytest
session loop. Tables are truncated after each test via a direct asyncpg connection
(not through SQLAlchemy) so the teardown is loop-independent.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import jwt as pyjwt
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

_TRUNCATE_SQL = """
    TRUNCATE support_tickets, conversations, conversation_threads,
             reminder_logs, reminders, audit_logs, ngo_settings, staff, ngos
    RESTART IDENTITY CASCADE
"""

_DB_DSN = (
    os.environ.get("TEST_DATABASE_URL", "")
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgresql+psycopg2://", "postgresql://")
)

ADMIN_KEY = "test-admin-key"
_STAFF_JWT_SECRET = "test-staff-jwt-secret"


@asynccontextmanager
async def _noop_lifespan(app):  # type: ignore[no-untyped-def]
    """No-op lifespan: skip init_db / close_db to avoid anyio loop conflicts."""
    yield


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------

def _mint_jwt(
    staff_id: str,
    ngo_id: str,
    ngo_slug: str,
    role: str = "admin",
    allowed_agents: list[str] | None = None,
    expires_in: timedelta = timedelta(hours=24),
) -> str:
    """Mint a signed HS256 JWT for test staff."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": staff_id,
        "ngo_id": ngo_id,
        "ngo_slug": ngo_slug,
        "role": role,
        "allowed_agents": allowed_agents if allowed_agents is not None else [
            "fundraising", "finance", "marketing", "hr", "compliance"
        ],
        "exp": now + expires_in,
        "iat": now,
    }
    return pyjwt.encode(payload, _STAFF_JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# DB cleanup — runs after every test
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def _clean_db() -> AsyncGenerator[None, None]:
    """
    Truncate all application tables after each test, then dispose the
    SQLAlchemy engine pool so the next test creates fresh asyncpg connections
    on its own event loop — preventing "Future attached to different loop" errors.
    """
    yield

    from app.core.database import engine

    if _DB_DSN:
        conn = await asyncpg.connect(_DB_DSN)
        try:
            await conn.execute(_TRUNCATE_SQL)
        finally:
            await conn.close()

    await engine.dispose()


# ---------------------------------------------------------------------------
# Base payloads
# ---------------------------------------------------------------------------

_BASE_NGO_PAYLOAD: dict[str, Any] = {
    "name": "Staff Test NGO",
    "telegram_bot_token": "9999999999:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ",
    "anthropic_api_key": "sk-ant-test-key",
    "timezone": "UTC",
    "language": "en",
}

_BASE_STAFF_PAYLOAD: dict[str, Any] = {
    "telegram_user_id": 111111111,
    "name": "Test Staff",
    "role": "admin",
    "allowed_agents": ["fundraising", "finance", "marketing", "hr", "compliance"],
    "email": "staff@testngo.org",
}


# ---------------------------------------------------------------------------
# Admin client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX async test client wired to the real FastAPI app.
    Lifespan is patched to a no-op so asyncpg connections are created on the
    pytest event loop (not anyio's internal loop).
    Telegram webhook is patched to prevent real HTTP calls.
    """
    with (
        patch.object(app.router, "lifespan_context", _noop_lifespan),
        patch(
            "app.api.v1.admin.ngos._register_telegram_webhook",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Admin-API-Key": ADMIN_KEY},
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Staff fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def ngo_and_staff(
    admin_client: AsyncClient,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Create an NGO and a staff member. Returns (ngo, staff, jwt_token)."""
    ngo_resp = await admin_client.post("/api/v1/admin/ngos", json=_BASE_NGO_PAYLOAD)
    assert ngo_resp.status_code == 201, ngo_resp.text
    ngo = ngo_resp.json()

    staff_resp = await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={**_BASE_STAFF_PAYLOAD, "ngo_id": ngo["id"]},
    )
    assert staff_resp.status_code == 201, staff_resp.text
    staff = staff_resp.json()

    token = _mint_jwt(staff["id"], ngo["id"], ngo["slug"])
    return ngo, staff, token


@pytest_asyncio.fixture
async def staff_client(
    ngo_and_staff: tuple[dict[str, Any], dict[str, Any], str],
) -> AsyncGenerator[tuple[AsyncClient, dict[str, Any], dict[str, Any]], None]:
    """Staff-authenticated HTTPX client. Yields (client, ngo, staff)."""
    ngo, staff, token = ngo_and_staff
    with (
        patch.object(app.router, "lifespan_context", _noop_lifespan),
        patch("app.api.v1.staff.reminders.send_to_group", new_callable=AsyncMock),
        patch("app.api.v1.staff.support.send_to_group", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, ngo, staff


@pytest_asyncio.fixture
async def peer_staff_client(
    admin_client: AsyncClient,
    ngo_and_staff: tuple[dict[str, Any], dict[str, Any], str],
) -> AsyncGenerator[tuple[AsyncClient, dict[str, Any], dict[str, Any]], None]:
    """A second staff member in the SAME NGO — for within-NGO isolation tests."""
    ngo, _, _ = ngo_and_staff
    staff_resp = await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={
            **_BASE_STAFF_PAYLOAD,
            "ngo_id": ngo["id"],
            "telegram_user_id": 333333333,
            "email": "peer@testngo.org",
        },
    )
    assert staff_resp.status_code == 201, staff_resp.text
    staff = staff_resp.json()
    token = _mint_jwt(staff["id"], ngo["id"], ngo["slug"])

    with (
        patch.object(app.router, "lifespan_context", _noop_lifespan),
        patch("app.api.v1.staff.reminders.send_to_group", new_callable=AsyncMock),
        patch("app.api.v1.staff.support.send_to_group", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, ngo, staff


@pytest_asyncio.fixture
async def second_ngo_and_staff(
    admin_client: AsyncClient,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """A second independent NGO + staff — for cross-NGO isolation tests."""
    ngo_resp = await admin_client.post("/api/v1/admin/ngos", json={
        **_BASE_NGO_PAYLOAD,
        "name": "Second Test NGO",
        "telegram_bot_token": "8888888888:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ",
    })
    assert ngo_resp.status_code == 201, ngo_resp.text
    ngo = ngo_resp.json()

    staff_resp = await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={
            **_BASE_STAFF_PAYLOAD,
            "ngo_id": ngo["id"],
            "telegram_user_id": 222222222,
            "email": "staff2@secondngo.org",
        },
    )
    assert staff_resp.status_code == 201, staff_resp.text
    staff = staff_resp.json()

    token = _mint_jwt(staff["id"], ngo["id"], ngo["slug"])
    return ngo, staff, token


@pytest_asyncio.fixture
async def second_staff_client(
    second_ngo_and_staff: tuple[dict[str, Any], dict[str, Any], str],
) -> AsyncGenerator[tuple[AsyncClient, dict[str, Any], dict[str, Any]], None]:
    """Staff client for the SECOND test NGO."""
    ngo, staff, token = second_ngo_and_staff
    with (
        patch.object(app.router, "lifespan_context", _noop_lifespan),
        patch("app.api.v1.staff.reminders.send_to_group", new_callable=AsyncMock),
        patch("app.api.v1.staff.support.send_to_group", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, ngo, staff
