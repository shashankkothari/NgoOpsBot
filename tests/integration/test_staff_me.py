"""
Tests for GET /api/v1/staff/me.

Covers:
- Unauthenticated → 401
- Returns correct name, role, ngo_name, ngo_slug, allowed_agents, email
"""

from __future__ import annotations

import pytest

_ME = "/api/v1/staff/me"


@pytest.mark.asyncio
async def test_me_unauthenticated_returns_401(admin_client):
    resp = await admin_client.get(_ME)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_200(staff_client):
    client, _, _ = staff_client
    resp = await client.get(_ME)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_me_returns_correct_name(staff_client):
    client, _, staff = staff_client
    body = (await client.get(_ME)).json()
    assert body["name"] == staff["name"]


@pytest.mark.asyncio
async def test_me_returns_correct_role(staff_client):
    client, _, staff = staff_client
    body = (await client.get(_ME)).json()
    assert body["role"] == staff["role"]


@pytest.mark.asyncio
async def test_me_returns_ngo_name(staff_client):
    client, ngo, _ = staff_client
    body = (await client.get(_ME)).json()
    assert body["ngo_name"] == ngo["name"]


@pytest.mark.asyncio
async def test_me_returns_ngo_slug(staff_client):
    client, ngo, _ = staff_client
    body = (await client.get(_ME)).json()
    assert body["ngo_slug"] == ngo["slug"]


@pytest.mark.asyncio
async def test_me_returns_allowed_agents(staff_client):
    client, _, staff = staff_client
    body = (await client.get(_ME)).json()
    assert sorted(body["allowed_agents"]) == sorted(staff["allowed_agents"])


@pytest.mark.asyncio
async def test_me_returns_email(staff_client):
    client, _, staff = staff_client
    body = (await client.get(_ME)).json()
    assert body["email"] == staff["email"]
