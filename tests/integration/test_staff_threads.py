"""
Staff conversation thread endpoint integration tests.

Covers:
- GET /api/v1/staff/threads     — list threads
- GET /api/v1/staff/threads/{id} — thread detail

These tests use the /staff/chat endpoint (with dispatch mocked) to create
real thread + conversation records in the DB before asserting on the
thread endpoints.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

_THREADS_URL = "/api/v1/staff/threads"
_CHAT_URL = "/api/v1/staff/chat"


@dataclass
class _FakeResponse:
    text: str = "Test agent reply"
    agent_name: str = "fundraising"
    input_tokens: int = 10
    output_tokens: int = 20
    language_detected: str | None = "en"
    cached: bool = False


# ---------------------------------------------------------------------------
# GET /threads — list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_threads_empty_initially(staff_client):
    client, _, _ = staff_client
    resp = await client.get(_THREADS_URL)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_threads_shows_thread_after_chat(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = _FakeResponse()
        await client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})

    resp = await client.get(_THREADS_URL)
    assert resp.status_code == 200
    threads = resp.json()
    assert len(threads) >= 1
    assert threads[0]["agent_name"] == "fundraising"


@pytest.mark.asyncio
async def test_list_threads_does_not_include_peer_threads(staff_client, peer_staff_client):
    """Staff member A should not see threads belonging to staff member B."""
    client_a, _, _ = staff_client
    client_b, _, _ = peer_staff_client

    # B creates a thread via chat
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = _FakeResponse()
        await client_b.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})

    # A's thread list should be empty
    threads_a = (await client_a.get(_THREADS_URL)).json()
    assert threads_a == []


# ---------------------------------------------------------------------------
# GET /threads/{id} — detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_nonexistent_thread_returns_404(staff_client):
    client, _, _ = staff_client
    resp = await client.get(f"{_THREADS_URL}/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_thread_detail_returns_messages(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = _FakeResponse()
        chat_resp = (
            await client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})
        ).json()

    thread_id = chat_resp["thread_id"]
    detail = (await client.get(f"{_THREADS_URL}/{thread_id}")).json()
    assert detail["id"] == thread_id
    assert isinstance(detail["messages"], list)
    assert len(detail["messages"]) >= 1


@pytest.mark.asyncio
async def test_get_thread_messages_have_correct_roles(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = _FakeResponse()
        chat_resp = (
            await client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})
        ).json()

    thread_id = chat_resp["thread_id"]
    messages = (await client.get(f"{_THREADS_URL}/{thread_id}")).json()["messages"]
    roles = {m["role"] for m in messages}
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_get_peer_thread_returns_404(staff_client, peer_staff_client):
    """A thread belonging to staff B is not accessible by staff A."""
    client_a, _, _ = staff_client
    client_b, _, _ = peer_staff_client

    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = _FakeResponse()
        chat_resp = (
            await client_b.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})
        ).json()

    thread_id = chat_resp["thread_id"]
    resp = await client_a.get(f"{_THREADS_URL}/{thread_id}")
    assert resp.status_code == 404
