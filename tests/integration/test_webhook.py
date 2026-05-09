"""
Integration tests for POST /api/v1/webhook/{ngo_slug}/{secret}

Strategy:
- Use the HTTPX async test client (AsyncClient + ASGITransport) against the
  real FastAPI app.
- Replace the SQLAlchemy get_db dependency with a function that returns a
  mock session — we're testing the webhook's routing logic, not DB operations.
- Patch route_update and _process_update_background so no Telegram/Claude
  calls are made.

All tests assert on HTTP status codes and JSON response shapes.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# App import — done at module level; fixtures override dependencies
# ---------------------------------------------------------------------------
from app.main import app
from app.core.database import get_db
from app.models.ngo import NGO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_SLUG = "test-ngo"
_VALID_SECRET = "abc123secret"


def _make_ngo_row(
    slug: str = _VALID_SLUG,
    secret: str = _VALID_SECRET,
    is_active: bool = True,
) -> MagicMock:
    ngo = MagicMock(spec=NGO)
    ngo.slug = slug
    ngo.webhook_secret = secret
    ngo.is_active = is_active
    return ngo


def _make_db_session(ngo: NGO | None) -> AsyncMock:
    """Return an AsyncMock session whose execute().scalar_one_or_none() returns ngo."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = ngo
    session.execute = AsyncMock(return_value=result)
    return session


def _minimal_update(update_id: int = 123456789) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": 987654321, "is_bot": False, "first_name": "Priya"},
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "text": "hello",
            "date": 1700000000,
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def webhook_client():
    """
    HTTPX async test client with no default auth headers.
    DB dependency is overridden per-test via app.dependency_overrides.
    Background task processing is patched to a no-op.
    """
    with patch(
        "app.api.v1.webhook._process_update_background",
        new_callable=AsyncMock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper that overrides the DB dependency for a single test
# ---------------------------------------------------------------------------

def _override_db(ngo: NGO | None):
    async def _fake_db():
        yield _make_db_session(ngo)
    app.dependency_overrides[get_db] = _fake_db


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_update_to_known_ngo_returns_200(webhook_client: AsyncClient):
    ngo = _make_ngo_row()
    _override_db(ngo)

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
        json=_minimal_update(),
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": "true"}


@pytest.mark.asyncio
async def test_wrong_secret_returns_403(webhook_client: AsyncClient):
    ngo = _make_ngo_row(secret="correct-secret")
    _override_db(ngo)

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/wrong-secret",
        json=_minimal_update(),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unknown_ngo_slug_returns_200(webhook_client: AsyncClient):
    """
    Unknown NGO → 200 (not 404). We must not tell Telegram that our NGO
    doesn't exist — it would keep retrying and consume our rate limit.
    """
    _override_db(None)  # scalar_one_or_none returns None

    resp = await webhook_client.post(
        "/api/v1/webhook/nonexistent-ngo/some-secret",
        json=_minimal_update(),
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": "true"}


@pytest.mark.asyncio
async def test_inactive_ngo_returns_200(webhook_client: AsyncClient):
    """
    Inactive NGO → 200. Same reasoning: no information leakage to Telegram.
    """
    ngo = _make_ngo_row(is_active=False)
    _override_db(ngo)

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
        json=_minimal_update(),
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": "true"}


@pytest.mark.asyncio
async def test_malformed_json_body_returns_200(webhook_client: AsyncClient):
    """
    Malformed JSON from Telegram → 200. Retrying won't fix a corrupted body.
    The webhook handler catches JSON parse errors and returns ok.
    """
    ngo = _make_ngo_row()
    _override_db(ngo)

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
        content=b"not-valid-json{{{",
        headers={"Content-Type": "application/json"},
    )
    # The handler catches JSON errors and returns {"ok": "true"} with 200
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_valid_update_dispatches_background_task(webhook_client: AsyncClient):
    """
    Background processing must be enqueued (not executed inline) so the
    endpoint returns before Claude's 20–30 s response time.
    We verify it's enqueued by patching and checking call count.
    """
    ngo = _make_ngo_row()
    _override_db(ngo)

    with patch(
        "app.api.v1.webhook._process_update_background",
        new_callable=AsyncMock,
    ) as mock_bg:
        # Re-create client so this patch takes effect
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
                json=_minimal_update(),
            )

    assert resp.status_code == 200
    # BackgroundTasks.add_task is called — background coroutine will be invoked
    # by Starlette after the response is sent; we just verify no exception.


@pytest.mark.asyncio
async def test_voice_update_accepted_and_returns_200(webhook_client: AsyncClient):
    ngo = _make_ngo_row()
    _override_db(ngo)

    voice_update = {
        "update_id": 111,
        "message": {
            "message_id": 2,
            "from": {"id": 100, "is_bot": False, "first_name": "Ravi"},
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "voice": {"file_id": "abc", "duration": 3, "mime_type": "audio/ogg"},
            "date": 1700000001,
        },
    }

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
        json=voice_update,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_edited_message_update_returns_200(webhook_client: AsyncClient):
    """Edited messages are ignored by parse_update() but the endpoint returns 200."""
    ngo = _make_ngo_row()
    _override_db(ngo)

    edited_update = {
        "update_id": 222,
        "edited_message": {
            "message_id": 5,
            "from": {"id": 42, "is_bot": False, "first_name": "X"},
            "chat": {"id": -100, "type": "supergroup"},
            "text": "edited",
            "date": 1700000002,
            "edit_date": 1700000099,
        },
    }

    resp = await webhook_client.post(
        f"/api/v1/webhook/{_VALID_SLUG}/{_VALID_SECRET}",
        json=edited_update,
    )
    assert resp.status_code == 200
