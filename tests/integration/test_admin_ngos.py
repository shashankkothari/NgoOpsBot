"""
Integration tests for the Admin NGO CRUD API.

Endpoint prefix: /api/v1/admin/ngos

Uses:
- Real async SQLite DB (in-memory via aiosqlite) through the conftest fixtures
- HTTPX async test client against the real FastAPI app
- Telegram setWebhook patched out (we don't want real HTTP calls in tests)

All tests require the X-Admin-API-Key header (enforced by NGOAuthMiddleware).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db
from app.models.ngo import NGO


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

ADMIN_KEY = "test-admin-key"
ADMIN_HEADERS = {"X-Admin-API-Key": ADMIN_KEY}

_BASE_CREATE_PAYLOAD = {
    "name": "Green Future NGO",
    "telegram_bot_token": "1234567890:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ",
    "anthropic_api_key": "sk-ant-test-key",
    "timezone": "Asia/Kolkata",
    "language": "en",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_client(async_session: AsyncSession):
    """
    HTTPX async test client wired to the test DB session and with the
    admin API key set in headers by default.
    Telegram webhook registration is patched to a no-op throughout.
    """
    async def _override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db

    with patch(
        "app.api.v1.admin.ngos._register_telegram_webhook",
        new_callable=AsyncMock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers=ADMIN_HEADERS,
        ) as client:
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper — create an NGO and return its JSON body
# ---------------------------------------------------------------------------

async def _create_ngo(client: AsyncClient, overrides: dict | None = None) -> dict:
    payload = {**_BASE_CREATE_PAYLOAD, **(overrides or {})}
    resp = await client.post("/api/v1/admin/ngos", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_admin_key_returns_401(async_session: AsyncSession):
    async def _override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            # No auth header
        ) as client:
            resp = await client.get("/api/v1/admin/ngos")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_wrong_admin_key_returns_401(async_session: AsyncSession):
    async def _override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Admin-API-Key": "wrong-key"},
        ) as client:
            resp = await client.get("/api/v1/admin/ngos")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Create NGO
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ngo_returns_201_with_id_and_slug(admin_client: AsyncClient):
    resp = await admin_client.post("/api/v1/admin/ngos", json=_BASE_CREATE_PAYLOAD)

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    # UUID is parseable
    uuid.UUID(body["id"])
    assert "slug" in body
    assert body["slug"] == "green-future-ngo"


@pytest.mark.asyncio
async def test_create_ngo_slug_is_url_safe(admin_client: AsyncClient):
    resp = await admin_client.post(
        "/api/v1/admin/ngos",
        json={**_BASE_CREATE_PAYLOAD, "name": "Help & Hope Charitable Trust!"},
    )
    assert resp.status_code == 201
    slug = resp.json()["slug"]
    # Slug must be lowercase, hyphen-separated, no special chars
    assert slug == slug.lower()
    assert " " not in slug
    assert "!" not in slug
    assert "&" not in slug


@pytest.mark.asyncio
async def test_create_ngo_with_duplicate_name_returns_409(admin_client: AsyncClient):
    await _create_ngo(admin_client)
    # Try again with the same name
    resp = await admin_client.post("/api/v1/admin/ngos", json=_BASE_CREATE_PAYLOAD)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# List NGOs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_ngos_returns_paginated_response(admin_client: AsyncClient):
    # Create two NGOs so the list is non-empty
    await _create_ngo(admin_client, {"name": "Alpha NGO"})
    await _create_ngo(admin_client, {"name": "Beta NGO"})

    resp = await admin_client.get("/api/v1/admin/ngos")
    assert resp.status_code == 200
    body = resp.json()

    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert isinstance(body["items"], list)
    assert body["total"] >= 2


@pytest.mark.asyncio
async def test_list_ngos_pagination_params_respected(admin_client: AsyncClient):
    for i in range(5):
        await _create_ngo(admin_client, {"name": f"NGO Page Test {i}"})

    resp = await admin_client.get("/api/v1/admin/ngos?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 2
    assert body["page"] == 1
    assert body["page_size"] == 2


# ---------------------------------------------------------------------------
# Get NGO by id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ngo_by_id_returns_200_with_settings(admin_client: AsyncClient):
    created = await _create_ngo(admin_client, {"name": "Detail Test NGO"})
    ngo_id = created["id"]

    resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ngo_id
    assert "settings" in body
    assert isinstance(body["settings"], list)


@pytest.mark.asyncio
async def test_get_nonexistent_ngo_returns_404(admin_client: AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/v1/admin/ngos/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update NGO (PATCH)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_ngo_timezone_returns_200_and_persists(admin_client: AsyncClient):
    created = await _create_ngo(admin_client, {"name": "Timezone Test NGO"})
    ngo_id = created["id"]

    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo_id}",
        json={"timezone": "America/New_York"},
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "America/New_York"

    # Re-fetch to verify DB persistence within the test session
    get_resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["timezone"] == "America/New_York"


@pytest.mark.asyncio
async def test_update_nonexistent_ngo_returns_404(admin_client: AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{fake_id}",
        json={"timezone": "UTC"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Soft delete NGO
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_delete_ngo_returns_204_and_sets_inactive(admin_client: AsyncClient):
    created = await _create_ngo(admin_client, {"name": "Delete Me NGO"})
    ngo_id = created["id"]

    del_resp = await admin_client.delete(f"/api/v1/admin/ngos/{ngo_id}")
    assert del_resp.status_code == 204

    # Verify is_active=False via GET
    get_resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_soft_delete_does_not_remove_row(admin_client: AsyncClient):
    """Soft delete keeps the row; GET still returns 200."""
    created = await _create_ngo(admin_client, {"name": "Soft Delete NGO"})
    ngo_id = created["id"]

    await admin_client.delete(f"/api/v1/admin/ngos/{ngo_id}")

    get_resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo_id}")
    assert get_resp.status_code == 200


# ---------------------------------------------------------------------------
# NGO Stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ngo_stats_returns_200_with_expected_fields(admin_client: AsyncClient):
    created = await _create_ngo(admin_client, {"name": "Stats Test NGO"})
    ngo_id = created["id"]

    resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo_id}/stats")
    assert resp.status_code == 200
    body = resp.json()

    # All required aggregate fields must be present
    assert "total_messages" in body
    assert "total_tokens" in body
    assert "active_staff_count" in body
    assert "reminder_count" in body
    assert "ngo_id" in body
    assert "ngo_slug" in body

    # A freshly created NGO has zero activity
    assert body["total_messages"] == 0
    assert body["total_tokens"] == 0
    assert body["active_staff_count"] == 0


@pytest.mark.asyncio
async def test_get_ngo_stats_for_nonexistent_ngo_returns_404(admin_client: AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/v1/admin/ngos/{fake_id}/stats")
    assert resp.status_code == 404
