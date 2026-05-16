"""
Staff JWT authentication guard tests.

Covers:
- Missing Bearer token → 401
- Expired JWT → 401
- JWT signed with wrong secret → 401
- Valid JWT for a deactivated staff member → 401
- Valid JWT → 200

Uses GET /api/v1/staff/me as the probe endpoint (simplest protected route).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.conftest import ADMIN_KEY, _mint_jwt, _noop_lifespan

_ME = "/api/v1/staff/me"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _unauthenticated_get(path: str) -> int:
    """Make a GET request with no Authorization header; return status code."""
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get(path)
    return resp.status_code


async def _get_with_token(path: str, token: str) -> int:
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get(path)
    return resp.status_code


# ---------------------------------------------------------------------------
# Missing token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_token_returns_401():
    assert await _unauthenticated_get(_ME) == 401


@pytest.mark.asyncio
async def test_no_token_body_has_detail():
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get(_ME)
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# Expired JWT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_jwt_returns_401(ngo_and_staff):
    _, staff, _ = ngo_and_staff
    ngo, _, _ = ngo_and_staff
    expired_token = _mint_jwt(
        staff["id"], ngo["id"], ngo["slug"],
        expires_in=timedelta(seconds=-1),
    )
    assert await _get_with_token(_ME, expired_token) == 401


# ---------------------------------------------------------------------------
# Tampered / wrong-secret JWT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wrong_secret_jwt_returns_401(ngo_and_staff):
    ngo, staff, _ = ngo_and_staff
    import jwt as pyjwt
    from datetime import datetime, timezone
    bad_token = pyjwt.encode(
        {"sub": staff["id"], "ngo_id": ngo["id"], "ngo_slug": ngo["slug"],
         "role": "admin", "allowed_agents": [], "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret",
        algorithm="HS256",
    )
    assert await _get_with_token(_ME, bad_token) == 401


@pytest.mark.asyncio
async def test_garbage_token_returns_401():
    assert await _get_with_token(_ME, "not.a.jwt") == 401


# ---------------------------------------------------------------------------
# Deactivated staff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivated_staff_jwt_returns_401(admin_client, ngo_and_staff):
    ngo, staff, token = ngo_and_staff

    # Deactivate the staff member via admin API
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}",
        json={"is_active": False},
    )
    assert resp.status_code == 200

    # The previously-valid JWT should now be rejected
    assert await _get_with_token(_ME, token) == 401


# ---------------------------------------------------------------------------
# Valid JWT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_jwt_returns_200(staff_client):
    client, _, _ = staff_client
    resp = await client.get(_ME)
    assert resp.status_code == 200
