"""
Unit tests for app.comms.sms

External dependencies mocked:
- httpx.AsyncClient.post  (MSG91 API calls)
- app.core.metrics        (Prometheus counters/histograms — avoid side effects)

Tests cover:
- normalize_phone() for all Indian number formats
- send_sms() request construction and return values on 200 / 429 / 500
- send_bulk_sms() respects the concurrency semaphore
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.comms.sms import normalize_phone, send_bulk_sms, send_sms


# ---------------------------------------------------------------------------
# normalize_phone()
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    def test_bare_10_digit_prepends_91(self):
        assert normalize_phone("9876543210") == "919876543210"

    def test_plus_prefix_is_stripped(self):
        assert normalize_phone("+919876543210") == "919876543210"

    def test_zero_prefixed_11_digit_normalized(self):
        assert normalize_phone("09876543210") == "919876543210"

    def test_already_normalized_12_digit_unchanged(self):
        assert normalize_phone("919876543210") == "919876543210"

    def test_dashes_and_spaces_stripped_before_normalizing(self):
        # Common WhatsApp-saved format: "+91 98765-43210"
        assert normalize_phone("+91 98765-43210") == "919876543210"

    def test_unknown_format_returned_as_digits_only(self):
        # Non-Indian 11-digit number — returned as-is (digits only)
        result = normalize_phone("+1 800 555 1234")
        assert result == "18005551234"


# ---------------------------------------------------------------------------
# send_sms() — mock httpx
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture(autouse=True)
def _patch_metrics():
    """Prevent Prometheus counter operations from failing in unit tests."""
    with (
        patch("app.comms.sms.external_api_latency") as lat,
        patch("app.comms.sms.reminders_sent") as sent,
    ):
        lat.labels.return_value.observe = MagicMock()
        sent.labels.return_value.inc = MagicMock()
        yield


@pytest.fixture(autouse=True)
def _patch_settings():
    """Provide dummy MSG91 credentials so settings.MSG91_* don't need env vars."""
    with patch("app.comms.sms.settings") as mock_settings:
        mock_settings.MSG91_API_KEY = "test-api-key"
        mock_settings.MSG91_SENDER_ID = "TESTBOT"
        yield mock_settings


@pytest.mark.asyncio
async def test_send_sms_returns_true_on_200():
    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(200))
        mock_get_client.return_value = mock_client

        result = await send_sms("9876543210", "Test message", "test-ngo")

    assert result is True


@pytest.mark.asyncio
async def test_send_sms_constructs_correct_msg91_payload():
    captured_kwargs: dict = {}

    async def _fake_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        return _mock_response(200)

    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        await send_sms("9876543210", "Hello NGO", "test-ngo")

    payload = captured_kwargs["json"]
    assert payload["route"] == "4"            # transactional route
    assert payload["country"] == "91"
    assert payload["sms"][0]["message"] == "Hello NGO"
    assert payload["sms"][0]["to"] == ["919876543210"]  # normalized

    headers = captured_kwargs["headers"]
    assert headers["authkey"] == "test-api-key"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_send_sms_uses_custom_sender_id_when_provided():
    captured_kwargs: dict = {}

    async def _fake_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        return _mock_response(200)

    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        await send_sms("9876543210", "Hello", "test-ngo", sender_id="CUSTOM")

    assert captured_kwargs["json"]["sender"] == "CUSTOM"


@pytest.mark.asyncio
async def test_send_sms_returns_false_on_429():
    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(429))
        mock_get_client.return_value = mock_client

        result = await send_sms("9876543210", "msg", "test-ngo")

    assert result is False


@pytest.mark.asyncio
async def test_send_sms_returns_false_on_500():
    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(500, "Internal Error"))
        mock_get_client.return_value = mock_client

        result = await send_sms("9876543210", "msg", "test-ngo")

    assert result is False


@pytest.mark.asyncio
async def test_send_sms_returns_false_on_network_error():
    import httpx

    with patch("app.comms.sms._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("connection refused", request=MagicMock())
        )
        mock_get_client.return_value = mock_client

        result = await send_sms("9876543210", "msg", "test-ngo")

    assert result is False


@pytest.mark.asyncio
async def test_send_sms_does_not_raise_on_any_http_error():
    """send_sms must never propagate exceptions — the caller only checks bool."""
    for status in (400, 401, 403, 404, 429, 500, 502, 503):
        with patch("app.comms.sms._get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(status))
            mock_get_client.return_value = mock_client

            result = await send_sms("9876543210", "msg", "test-ngo")
            assert isinstance(result, bool), f"Expected bool for status {status}"


# ---------------------------------------------------------------------------
# send_bulk_sms() — concurrency semaphore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_bulk_sms_returns_sent_and_failed_counts():
    call_count = 0

    async def _fake_send(phone, message, ngo_slug, sender_id=None):
        nonlocal call_count
        call_count += 1
        return call_count % 2 == 1  # alternates True / False

    with patch("app.comms.sms.send_sms", side_effect=_fake_send):
        recipients = [
            {"phone": "9876543210", "name": "Alice"},
            {"phone": "9876543211", "name": "Bob"},
            {"phone": "9876543212", "name": "Carol"},
            {"phone": "9876543213", "name": "Dave"},
        ]
        result = await send_bulk_sms(recipients, "Hello {name}!", "test-ngo")

    assert result["sent"] + result["failed"] == 4
    assert result["sent"] == 2
    assert result["failed"] == 2


@pytest.mark.asyncio
async def test_send_bulk_sms_respects_semaphore_concurrency_limit():
    """
    Verify that send_bulk_sms limits concurrent send_sms calls.

    The module-level _BULK_SEMAPHORE is recreated here (bound to the test's
    event loop) with limit=5 so we can assert that peak concurrency stays at
    or below that limit even with 20 recipients.
    """
    import app.comms.sms as sms_module

    LIMIT = 5
    fresh_semaphore = asyncio.Semaphore(LIMIT)

    peak_concurrent = 0
    current_concurrent = 0

    async def _fake_send(phone, message, ngo_slug, sender_id=None):
        nonlocal peak_concurrent, current_concurrent
        current_concurrent += 1
        if current_concurrent > peak_concurrent:
            peak_concurrent = current_concurrent
        await asyncio.sleep(0)
        current_concurrent -= 1
        return True

    with (
        patch.object(sms_module, "_BULK_SEMAPHORE", fresh_semaphore),
        patch("app.comms.sms.send_sms", side_effect=_fake_send),
    ):
        recipients = [{"phone": f"987654{i:04d}", "name": f"Person{i}"} for i in range(20)]
        await send_bulk_sms(recipients, "Hi {name}", "test-ngo")

    assert peak_concurrent <= LIMIT


@pytest.mark.asyncio
async def test_send_bulk_sms_all_success():
    with patch("app.comms.sms.send_sms", return_value=True):
        recipients = [{"phone": "9876543210", "name": "A"}, {"phone": "9876543211", "name": "B"}]
        result = await send_bulk_sms(recipients, "Msg for {name}", "test-ngo")

    assert result == {"sent": 2, "failed": 0, "errors": []}


@pytest.mark.asyncio
async def test_send_bulk_sms_all_fail():
    with patch("app.comms.sms.send_sms", return_value=False):
        recipients = [{"phone": "9876543210", "name": "A"}]
        result = await send_bulk_sms(recipients, "Msg for {name}", "test-ngo")

    assert result["sent"] == 0
    assert result["failed"] == 1
    assert len(result["errors"]) == 1
