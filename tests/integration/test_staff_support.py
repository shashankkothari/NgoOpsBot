"""
Staff support ticket endpoint integration tests.

Covers:
- POST /api/v1/staff/support
  - unauthenticated → 401
  - create returns 201, status=open, correct fields

- GET /api/v1/staff/support
  - unauthenticated → 401
  - returns only the authenticated staff member's own tickets
  - another staff in the same NGO cannot see each other's tickets
  - cross-NGO: staff from NGO B cannot see NGO A's tickets
"""

from __future__ import annotations

import pytest

_BASE_URL = "/api/v1/staff/support"

_TICKET_PAYLOAD = {
    "title": "Cannot access Google Drive",
    "description": "Getting a 403 error when trying to open the shared folder.",
    "category": "technical",
    "priority": "medium",
}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ticket_unauthenticated_returns_401(admin_client):
    resp = await admin_client.post(_BASE_URL, json=_TICKET_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_tickets_unauthenticated_returns_401(admin_client):
    resp = await admin_client.get(_BASE_URL)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST — create ticket
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ticket_returns_201(staff_client):
    client, _, _ = staff_client
    resp = await client.post(_BASE_URL, json=_TICKET_PAYLOAD)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_ticket_status_is_open(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()
    assert body["status"] == "open"


@pytest.mark.asyncio
async def test_create_ticket_title_matches(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()
    assert body["title"] == _TICKET_PAYLOAD["title"]


@pytest.mark.asyncio
async def test_create_ticket_category_matches(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()
    assert body["category"] == _TICKET_PAYLOAD["category"]


@pytest.mark.asyncio
async def test_create_ticket_has_id(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()
    import uuid
    uuid.UUID(body["id"])


# ---------------------------------------------------------------------------
# GET — list tickets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tickets_returns_200(staff_client):
    client, _, _ = staff_client
    resp = await client.get(_BASE_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_tickets_empty_initially(staff_client):
    client, _, _ = staff_client
    body = (await client.get(_BASE_URL)).json()
    assert body == []


@pytest.mark.asyncio
async def test_list_tickets_includes_own_ticket(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()
    listed = (await client.get(_BASE_URL)).json()
    assert any(t["id"] == created["id"] for t in listed)


@pytest.mark.asyncio
async def test_list_tickets_excludes_peer_tickets(staff_client, peer_staff_client):
    """Staff member A should not see tickets created by staff member B in the same NGO."""
    client_a, _, _ = staff_client
    client_b, _, _ = peer_staff_client

    # B creates a ticket
    created_by_b = (await client_b.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()

    # A should NOT see B's ticket
    listed_by_a = (await client_a.get(_BASE_URL)).json()
    assert all(t["id"] != created_by_b["id"] for t in listed_by_a)


@pytest.mark.asyncio
async def test_cross_ngo_tickets_not_visible(staff_client, second_staff_client):
    client_a, _, _ = staff_client
    client_b, _, _ = second_staff_client

    # NGO A creates a ticket
    created = (await client_a.post(_BASE_URL, json=_TICKET_PAYLOAD)).json()

    # NGO B staff should not see it
    listed = (await client_b.get(_BASE_URL)).json()
    assert all(t["id"] != created["id"] for t in listed)
