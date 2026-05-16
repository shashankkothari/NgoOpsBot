"""
Admin staff CRUD integration tests.

Endpoint prefix: /api/v1/admin/ngos/{ngo_id}/staff
Auth: X-Admin-API-Key

Covers:
- POST   /{ngo_id}/staff       → 201, staff created
- POST   /{ngo_id}/staff       → 409, duplicate telegram_user_id in same NGO
- GET    /{ngo_id}/staff       → 200, paginated list
- GET    /{ngo_id}/staff       → 404 for unknown NGO
- GET    /{ngo_id}/staff?is_active=false → filtered list
- PATCH  /{ngo_id}/staff/{id} → 200, updated fields
- DELETE /{ngo_id}/staff/{id} → 204, soft-delete (is_active=False)
- All endpoints require X-Admin-API-Key
"""

from __future__ import annotations

import uuid

import pytest

_BASE_STAFF = {
    "telegram_user_id": 555555555,
    "name": "Admin Created Staff",
    "role": "staff",
    "allowed_agents": ["fundraising", "finance"],
    "email": "newstaff@testngo.org",
}

_BASE_NGO = {
    "name": "Admin Staff Test NGO",
    "telegram_bot_token": "7777777777:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ",
    "anthropic_api_key": "sk-ant-admin-staff-test",
    "timezone": "UTC",
    "language": "en",
}


async def _create_ngo(admin_client) -> dict:
    resp = await admin_client.post("/api/v1/admin/ngos", json=_BASE_NGO)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_staff(admin_client, ngo_id: str, overrides: dict | None = None) -> dict:
    payload = {**_BASE_STAFF, "ngo_id": ngo_id, **(overrides or {})}
    resp = await admin_client.post(f"/api/v1/admin/ngos/{ngo_id}/staff", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_staff_requires_admin_key(ngo_and_staff):
    from unittest.mock import patch
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from tests.integration.conftest import _noop_lifespan

    ngo, _, _ = ngo_and_staff
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                f"/api/v1/admin/ngos/{ngo['id']}/staff",
                json={**_BASE_STAFF, "ngo_id": ngo["id"]},
            )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST — add staff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_staff_returns_201(admin_client):
    ngo = await _create_ngo(admin_client)
    resp = await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={**_BASE_STAFF, "ngo_id": ngo["id"]},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_add_staff_returns_id(admin_client):
    ngo = await _create_ngo(admin_client)
    body = (await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={**_BASE_STAFF, "ngo_id": ngo["id"]},
    )).json()
    uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_add_staff_returns_correct_name(admin_client):
    ngo = await _create_ngo(admin_client)
    body = await _create_staff(admin_client, ngo["id"])
    assert body["name"] == _BASE_STAFF["name"]


@pytest.mark.asyncio
async def test_add_staff_returns_correct_role(admin_client):
    ngo = await _create_ngo(admin_client)
    body = await _create_staff(admin_client, ngo["id"])
    assert body["role"] == _BASE_STAFF["role"]


@pytest.mark.asyncio
async def test_add_staff_is_active_true(admin_client):
    ngo = await _create_ngo(admin_client)
    body = await _create_staff(admin_client, ngo["id"])
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_add_staff_returns_allowed_agents(admin_client):
    ngo = await _create_ngo(admin_client)
    body = await _create_staff(admin_client, ngo["id"])
    assert sorted(body["allowed_agents"]) == sorted(_BASE_STAFF["allowed_agents"])


@pytest.mark.asyncio
async def test_add_staff_duplicate_telegram_id_returns_409(admin_client):
    ngo = await _create_ngo(admin_client)
    await _create_staff(admin_client, ngo["id"])

    # Second staff with same telegram_user_id in the same NGO
    resp = await admin_client.post(
        f"/api/v1/admin/ngos/{ngo['id']}/staff",
        json={**_BASE_STAFF, "ngo_id": ngo["id"], "email": "other@example.com"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_staff_to_nonexistent_ngo_returns_404(admin_client):
    fake_id = uuid.uuid4()
    resp = await admin_client.post(
        f"/api/v1/admin/ngos/{fake_id}/staff",
        json={**_BASE_STAFF, "ngo_id": str(fake_id)},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET — list staff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_staff_returns_200(admin_client):
    ngo = await _create_ngo(admin_client)
    resp = await admin_client.get(f"/api/v1/admin/ngos/{ngo['id']}/staff")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_staff_returns_paginated_shape(admin_client):
    ngo = await _create_ngo(admin_client)
    body = (await admin_client.get(f"/api/v1/admin/ngos/{ngo['id']}/staff")).json()
    for key in ("items", "total", "page", "page_size"):
        assert key in body, f"Missing key: {key}"
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_staff_includes_created_member(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    body = (await admin_client.get(f"/api/v1/admin/ngos/{ngo['id']}/staff")).json()
    ids = [s["id"] for s in body["items"]]
    assert staff["id"] in ids


@pytest.mark.asyncio
async def test_list_staff_unknown_ngo_returns_404(admin_client):
    resp = await admin_client.get(f"/api/v1/admin/ngos/{uuid.uuid4()}/staff")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_staff_filter_active_only(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])

    # Deactivate the staff member
    await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}",
        json={"is_active": False},
    )

    body = (await admin_client.get(
        f"/api/v1/admin/ngos/{ngo['id']}/staff?is_active=true"
    )).json()
    assert all(s["is_active"] for s in body["items"])
    assert all(s["id"] != staff["id"] for s in body["items"])


# ---------------------------------------------------------------------------
# PATCH — update staff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_staff_name_returns_200(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}",
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_staff_allowed_agents(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    new_agents = ["hr", "compliance"]
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}",
        json={"allowed_agents": new_agents},
    )
    assert resp.status_code == 200
    assert sorted(resp.json()["allowed_agents"]) == sorted(new_agents)


@pytest.mark.asyncio
async def test_update_staff_role(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}",
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_update_nonexistent_staff_returns_404(admin_client):
    ngo = await _create_ngo(admin_client)
    resp = await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{uuid.uuid4()}",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE — deactivate staff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_staff_returns_204(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    resp = await admin_client.delete(f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_deactivate_staff_sets_is_active_false(admin_client):
    ngo = await _create_ngo(admin_client)
    staff = await _create_staff(admin_client, ngo["id"])
    await admin_client.delete(f"/api/v1/admin/ngos/{ngo['id']}/staff/{staff['id']}")

    body = (await admin_client.get(f"/api/v1/admin/ngos/{ngo['id']}/staff")).json()
    member = next((s for s in body["items"] if s["id"] == staff["id"]), None)
    assert member is not None
    assert member["is_active"] is False


@pytest.mark.asyncio
async def test_deactivate_nonexistent_staff_returns_404(admin_client):
    ngo = await _create_ngo(admin_client)
    resp = await admin_client.delete(
        f"/api/v1/admin/ngos/{ngo['id']}/staff/{uuid.uuid4()}"
    )
    assert resp.status_code == 404
