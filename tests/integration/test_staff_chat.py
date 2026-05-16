"""
Staff chat endpoint integration tests.

POST /api/v1/staff/chat

The Anthropic dispatch call is mocked in all tests so no real API key is needed.

Covers:
- Unauthenticated → 401
- Agent not in staff's allowed_agents → 403
- Unknown agent name → 400 (AgentNotFoundError)
- Agent disabled for the NGO → 403 (AgentNotEnabledError)
- Inactive NGO → 403
- Successful dispatch → 200 with reply, thread_id, agent_name
- Conversation turns are persisted (follow-up has prior history)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.dispatcher import AgentNotEnabledError, AgentNotFoundError
from tests.integration.conftest import _mint_jwt, _noop_lifespan

_CHAT_URL = "/api/v1/staff/chat"


@dataclass
class _FakeResponse:
    text: str = "Here is the fundraising advice."
    agent_name: str = "fundraising"
    input_tokens: int = 15
    output_tokens: int = 25
    language_detected: str | None = "en"
    cached: bool = False


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_unauthenticated_returns_401(admin_client):
    resp = await admin_client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hi"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Agent permission checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_agent_not_in_allowed_agents_returns_403(admin_client, ngo_and_staff):
    """Staff with restricted allowed_agents cannot access an agent outside the list."""
    from unittest.mock import patch as _patch
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    ngo, staff, _ = ngo_and_staff

    # Mint a token restricted to only finance
    restricted_token = _mint_jwt(
        staff["id"], ngo["id"], ngo["slug"],
        allowed_agents=["finance"],
    )

    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {restricted_token}"},
        ) as client:
            resp = await client.post(
                _CHAT_URL,
                json={"agent_name": "fundraising", "message": "Hello"},
            )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_unknown_agent_returns_400(staff_client):
    client, _, _ = staff_client
    with patch(
        "app.api.v1.staff.chat.dispatch",
        new_callable=AsyncMock,
        side_effect=AgentNotFoundError("no such agent"),
    ):
        resp = await client.post(_CHAT_URL, json={"agent_name": "unknown_agent", "message": "Hi"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_disabled_agent_returns_403(staff_client):
    client, _, _ = staff_client
    with patch(
        "app.api.v1.staff.chat.dispatch",
        new_callable=AsyncMock,
        side_effect=AgentNotEnabledError("agent disabled"),
    ):
        resp = await client.post(
            _CHAT_URL, json={"agent_name": "fundraising", "message": "Hi"}
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_inactive_ngo_returns_403(admin_client, ngo_and_staff):
    """Deactivating the NGO should block further chat requests."""
    from unittest.mock import patch as _patch
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    ngo, staff, token = ngo_and_staff

    # Deactivate the NGO
    await admin_client.patch(f"/api/v1/admin/ngos/{ngo['id']}", json={"is_active": False})

    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
                mock_d.return_value = _FakeResponse()
                resp = await client.post(
                    _CHAT_URL, json={"agent_name": "fundraising", "message": "Hi"}
                )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Successful dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_success_returns_200(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
        mock_d.return_value = _FakeResponse()
        resp = await client.post(
            _CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"}
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_success_returns_reply(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
        mock_d.return_value = _FakeResponse(text="Great fundraising idea!")
        body = (await client.post(
            _CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"}
        )).json()
    assert body["reply"] == "Great fundraising idea!"


@pytest.mark.asyncio
async def test_chat_success_returns_agent_name(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
        mock_d.return_value = _FakeResponse(agent_name="fundraising")
        body = (await client.post(
            _CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"}
        )).json()
    assert body["agent_name"] == "fundraising"


@pytest.mark.asyncio
async def test_chat_success_returns_thread_id(staff_client):
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
        mock_d.return_value = _FakeResponse()
        body = (await client.post(
            _CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"}
        )).json()
    # thread_id must be a valid UUID string
    uuid.UUID(body["thread_id"])


@pytest.mark.asyncio
async def test_chat_second_message_includes_history(staff_client):
    """dispatch is called with non-empty conversation_history on the second turn."""
    client, _, _ = staff_client
    with patch("app.api.v1.staff.chat.dispatch", new_callable=AsyncMock) as mock_d:
        mock_d.return_value = _FakeResponse()
        await client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Hello"})
        await client.post(_CHAT_URL, json={"agent_name": "fundraising", "message": "Follow up"})

    # Second call should have been given a non-empty history
    second_call_kwargs = mock_d.call_args_list[1].kwargs
    assert len(second_call_kwargs.get("conversation_history", [])) > 0
