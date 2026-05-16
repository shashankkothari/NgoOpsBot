"""
Staff reminder endpoint integration tests.

Covers:
- POST /api/v1/staff/reminders
  - one_time → reminder_type=date_based
  - daily/weekly/monthly → reminder_type=recurring
  - invalid repeat value → 422
  - invalid assignee_type → 422
  - empty assignee_ids on specific type (silent data loss — documents known behaviour)

- GET /api/v1/staff/reminders
  - staff_group reminders visible to all staff in the NGO
  - inactive reminders excluded
  - specific reminders only visible to targeted staff, not peers in the same NGO
  - cross-NGO: staff from NGO B cannot see NGO A's reminders

- POST /api/v1/staff/reminders/{id}/acknowledge
  - 200 + {"status": "acknowledged"}
  - reminder is marked inactive
  - recurring reminder is permanently deactivated (known behaviour, not a fix)
  - nonexistent reminder → 404

- POST /api/v1/staff/reminders/{id}/snooze
  - 200 + {"status": "snoozed", "next_fire_at": <future iso>}
  - next_fire_at advances by requested hours
  - duration_hours=0 → 422
  - duration_hours=169 → 422 (above 168 max)
  - nonexistent reminder → 404
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

_BASE_URL = "/api/v1/staff/reminders"

_SCHEDULED_AT = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

_ONE_TIME_PAYLOAD = {
    "title": "Submit report",
    "message": "Please submit the weekly report.",
    "scheduled_at": _SCHEDULED_AT,
    "repeat": "one_time",
    "assignee_type": "all",
    "assignee_ids": [],
    "snooze_options_hours": [1, 4],
}


# ---------------------------------------------------------------------------
# POST — create reminder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_reminder_returns_201(staff_client):
    client, _, _ = staff_client
    resp = await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_reminder_has_id(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    uuid.UUID(body["id"])  # raises if not a valid UUID


@pytest.mark.asyncio
async def test_create_one_time_maps_to_date_based(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    assert body["reminder_type"] == "date_based"


@pytest.mark.asyncio
async def test_create_daily_maps_to_recurring(staff_client):
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "repeat": "daily"}
    body = (await client.post(_BASE_URL, json=payload)).json()
    assert body["reminder_type"] == "recurring"


@pytest.mark.asyncio
async def test_create_weekly_maps_to_recurring(staff_client):
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "repeat": "weekly"}
    body = (await client.post(_BASE_URL, json=payload)).json()
    assert body["reminder_type"] == "recurring"


@pytest.mark.asyncio
async def test_create_monthly_maps_to_recurring(staff_client):
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "repeat": "monthly"}
    body = (await client.post(_BASE_URL, json=payload)).json()
    assert body["reminder_type"] == "recurring"


@pytest.mark.asyncio
async def test_create_is_active_true(staff_client):
    client, _, _ = staff_client
    body = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_create_invalid_repeat_returns_422(staff_client):
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "repeat": "hourly"}
    resp = await client.post(_BASE_URL, json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_assignee_type_returns_422(staff_client):
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "assignee_type": "everyone"}
    resp = await client.post(_BASE_URL, json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET — list reminders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_reminders_returns_200(staff_client):
    client, _, _ = staff_client
    resp = await client.get(_BASE_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_reminders_empty_initially(staff_client):
    client, _, _ = staff_client
    body = (await client.get(_BASE_URL)).json()
    assert body == []


@pytest.mark.asyncio
async def test_list_shows_staff_group_reminder(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    listed = (await client.get(_BASE_URL)).json()
    ids = [r["id"] for r in listed]
    assert created["id"] in ids


@pytest.mark.asyncio
async def test_list_excludes_inactive_reminders(staff_client, admin_client):
    client, ngo, _ = staff_client

    # Create via staff API
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()

    # Deactivate via admin API
    await admin_client.patch(
        f"/api/v1/admin/ngos/{ngo['id']}/reminders/{created['id']}",
        json={"is_active": False},
    )

    listed = (await client.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed)


@pytest.mark.asyncio
async def test_specific_reminder_visible_to_targeted_staff(staff_client):
    client, _, staff = staff_client
    payload = {
        **_ONE_TIME_PAYLOAD,
        "assignee_type": "specific",
        "assignee_ids": [staff["id"]],
    }
    created = (await client.post(_BASE_URL, json=payload)).json()
    listed = (await client.get(_BASE_URL)).json()
    assert any(r["id"] == created["id"] for r in listed)


@pytest.mark.asyncio
async def test_specific_reminder_not_visible_to_peer_staff(staff_client, peer_staff_client):
    client, _, staff = staff_client
    peer_client, _, _ = peer_staff_client

    # Create a reminder targeted only at the first staff member
    payload = {
        **_ONE_TIME_PAYLOAD,
        "assignee_type": "specific",
        "assignee_ids": [staff["id"]],
    }
    created = (await client.post(_BASE_URL, json=payload)).json()

    # Peer staff in the same NGO should NOT see this reminder
    listed = (await peer_client.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed)


@pytest.mark.asyncio
async def test_empty_assignee_ids_on_specific_creates_invisible_reminder(staff_client, peer_staff_client):
    """
    Known behaviour: creating a specific reminder with no assignee_ids
    succeeds but the reminder is never shown to anyone — not to the creator,
    not to peers. There is no error or warning.
    """
    client, _, _ = staff_client
    peer_client, _, _ = peer_staff_client

    payload = {
        **_ONE_TIME_PAYLOAD,
        "assignee_type": "specific",
        "assignee_ids": [],
    }
    created = (await client.post(_BASE_URL, json=payload)).json()
    assert created["id"]  # created successfully

    # Neither the creator nor a peer sees it
    listed_creator = (await client.get(_BASE_URL)).json()
    listed_peer = (await peer_client.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed_creator)
    assert all(r["id"] != created["id"] for r in listed_peer)


@pytest.mark.asyncio
async def test_cross_ngo_reminders_not_visible(staff_client, second_staff_client):
    client_a, _, _ = staff_client
    client_b, _, _ = second_staff_client

    # NGO A creates a reminder
    created = (await client_a.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()

    # NGO B staff should not see NGO A's reminder
    listed = (await client_b.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed)


# ---------------------------------------------------------------------------
# POST — acknowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledge_returns_200(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    resp = await client.post(f"{_BASE_URL}/{created['id']}/acknowledge")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_acknowledge_returns_acknowledged_status(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    body = (await client.post(f"{_BASE_URL}/{created['id']}/acknowledge")).json()
    assert body["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_acknowledge_marks_reminder_inactive(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    await client.post(f"{_BASE_URL}/{created['id']}/acknowledge")

    # The reminder should no longer appear in the active list
    listed = (await client.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed)


@pytest.mark.asyncio
async def test_acknowledge_recurring_reminder_permanently_deactivates(staff_client):
    """
    Known behaviour: acknowledging a recurring (daily/weekly) reminder sets
    is_active=False permanently. It does not reschedule — the reminder is gone.
    """
    client, _, _ = staff_client
    payload = {**_ONE_TIME_PAYLOAD, "repeat": "daily"}
    created = (await client.post(_BASE_URL, json=payload)).json()
    assert created["reminder_type"] == "recurring"

    await client.post(f"{_BASE_URL}/{created['id']}/acknowledge")

    listed = (await client.get(_BASE_URL)).json()
    assert all(r["id"] != created["id"] for r in listed)


@pytest.mark.asyncio
async def test_acknowledge_nonexistent_returns_404(staff_client):
    client, _, _ = staff_client
    resp = await client.post(f"{_BASE_URL}/{uuid.uuid4()}/acknowledge")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST — snooze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snooze_returns_200(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    resp = await client.post(
        f"{_BASE_URL}/{created['id']}/snooze",
        json={"duration_hours": 2},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_snooze_returns_snoozed_status(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    body = (await client.post(
        f"{_BASE_URL}/{created['id']}/snooze",
        json={"duration_hours": 2},
    )).json()
    assert body["status"] == "snoozed"


@pytest.mark.asyncio
async def test_snooze_returns_next_fire_at(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    before = datetime.now(timezone.utc)
    body = (await client.post(
        f"{_BASE_URL}/{created['id']}/snooze",
        json={"duration_hours": 3},
    )).json()
    after = datetime.now(timezone.utc)

    next_fire = datetime.fromisoformat(body["next_fire_at"])
    assert before + timedelta(hours=3) <= next_fire <= after + timedelta(hours=3)


@pytest.mark.asyncio
async def test_snooze_zero_hours_returns_422(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    resp = await client.post(
        f"{_BASE_URL}/{created['id']}/snooze",
        json={"duration_hours": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_snooze_above_max_returns_422(staff_client):
    client, _, _ = staff_client
    created = (await client.post(_BASE_URL, json=_ONE_TIME_PAYLOAD)).json()
    resp = await client.post(
        f"{_BASE_URL}/{created['id']}/snooze",
        json={"duration_hours": 169},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_snooze_nonexistent_returns_404(staff_client):
    client, _, _ = staff_client
    resp = await client.post(
        f"{_BASE_URL}/{uuid.uuid4()}/snooze",
        json={"duration_hours": 1},
    )
    assert resp.status_code == 404
