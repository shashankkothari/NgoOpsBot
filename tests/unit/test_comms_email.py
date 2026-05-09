"""
Unit tests for app.comms.email

External dependencies mocked:
- httpx.AsyncClient.post  (SendGrid API)
- app.core.metrics        (Prometheus counters/histograms)

Tests cover:
- mask_email() hides the domain
- text_to_html() newline conversion and HTML escaping
- send_email() Authorization header, from address, return value on 202/4xx/5xx
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.comms.email import mask_email, send_email, text_to_html


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_ngo(name: str = "Test NGO", slug: str = "test-ngo") -> MagicMock:
    ngo = MagicMock()
    ngo.name = name
    ngo.slug = slug
    return ngo


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture(autouse=True)
def _patch_metrics():
    with (
        patch("app.comms.email.external_api_latency") as lat,
        patch("app.comms.email.reminders_sent") as sent,
    ):
        lat.labels.return_value.observe = MagicMock()
        sent.labels.return_value.inc = MagicMock()
        yield


@pytest.fixture(autouse=True)
def _patch_settings():
    with patch("app.comms.email.settings") as mock_settings:
        mock_settings.SENDGRID_API_KEY = "SG.test-key"
        yield mock_settings


# ---------------------------------------------------------------------------
# mask_email()
# ---------------------------------------------------------------------------

class TestMaskEmail:
    def test_hides_domain_tld_only(self):
        # Format: localpart@***.tld
        result = mask_email("priya@testngo.org")
        assert result == "priya@***.org"

    def test_preserves_local_part(self):
        result = mask_email("admin@example.com")
        assert result.startswith("admin@")

    def test_multi_dot_domain_shows_only_tld(self):
        result = mask_email("user@mail.subdomain.io")
        assert result.endswith(".io")
        assert "subdomain" not in result

    def test_invalid_email_returns_stars(self):
        assert mask_email("notanemail") == "***"

    def test_empty_string_returns_stars(self):
        assert mask_email("") == "***"


# ---------------------------------------------------------------------------
# text_to_html()
# ---------------------------------------------------------------------------

class TestTextToHtml:
    def test_newline_converted_to_br(self):
        result = text_to_html("line one\nline two")
        assert "<br>" in result
        assert "line one" in result
        assert "line two" in result

    def test_script_tag_escaped(self):
        result = text_to_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_ampersand_escaped(self):
        result = text_to_html("foo & bar")
        assert "&amp;" in result
        assert " & " not in result

    def test_greater_than_escaped(self):
        result = text_to_html("a > b")
        assert "&gt;" in result

    def test_url_wrapped_in_anchor_tag(self):
        result = text_to_html("Visit https://example.com for info")
        assert '<a href="https://example.com">' in result

    def test_plain_text_unchanged_modulo_escaping(self):
        result = text_to_html("Hello world")
        assert "Hello world" in result

    def test_multiple_newlines_all_converted(self):
        result = text_to_html("a\nb\nc")
        assert result.count("<br>") == 2


# ---------------------------------------------------------------------------
# send_email() — mock httpx
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_returns_true_on_202():
    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(202))
        mock_get_client.return_value = mock_client

        result = await send_email(
            to_email="priya@testngo.org",
            to_name="Priya",
            subject="Test Subject",
            body="Hello Priya",
            ngo=_make_ngo(),
        )

    assert result is True


@pytest.mark.asyncio
async def test_send_email_uses_bearer_authorization_header():
    captured: dict = {}

    async def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _mock_response(202)

    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        await send_email(
            to_email="priya@testngo.org",
            to_name="Priya",
            subject="Subject",
            body="Body",
            ngo=_make_ngo(),
        )

    assert captured["headers"]["Authorization"] == "Bearer SG.test-key"
    assert captured["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_send_email_uses_platform_from_address():
    captured: dict = {}

    async def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _mock_response(202)

    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        ngo = _make_ngo(name="Greenfield NGO")
        await send_email(
            to_email="recipient@example.com",
            to_name="Recipient",
            subject="Hi",
            body="Hello",
            ngo=ngo,
        )

    from_block = captured["json"]["from"]
    # The from address must be the platform constant, not a user-supplied value
    assert from_block["email"] == "ngoopsbot@ngoopsbot.com"
    # The from name includes the NGO name
    assert "Greenfield NGO" in from_block["name"]


@pytest.mark.asyncio
async def test_send_email_payload_contains_plain_and_html_content():
    captured: dict = {}

    async def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _mock_response(202)

    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        await send_email(
            to_email="a@b.com",
            to_name="A",
            subject="S",
            body="Line one\nLine two",
            ngo=_make_ngo(),
        )

    content = captured["json"]["content"]
    types = {c["type"] for c in content}
    assert "text/plain" in types
    assert "text/html" in types


@pytest.mark.asyncio
async def test_send_email_includes_cc_when_provided():
    captured: dict = {}

    async def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _mock_response(202)

    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_get_client.return_value = mock_client

        await send_email(
            to_email="a@b.com",
            to_name="A",
            subject="S",
            body="B",
            ngo=_make_ngo(),
            cc=["cc@example.com"],
        )

    personalization = captured["json"]["personalizations"][0]
    assert "cc" in personalization
    assert personalization["cc"][0]["email"] == "cc@example.com"


@pytest.mark.asyncio
async def test_send_email_returns_false_on_400():
    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(400, "Bad Request"))
        mock_get_client.return_value = mock_client

        result = await send_email("a@b.com", "A", "S", "B", _make_ngo())

    assert result is False


@pytest.mark.asyncio
async def test_send_email_returns_false_on_429():
    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(429))
        mock_get_client.return_value = mock_client

        result = await send_email("a@b.com", "A", "S", "B", _make_ngo())

    assert result is False


@pytest.mark.asyncio
async def test_send_email_returns_false_on_500():
    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(500))
        mock_get_client.return_value = mock_client

        result = await send_email("a@b.com", "A", "S", "B", _make_ngo())

    assert result is False


@pytest.mark.asyncio
async def test_send_email_returns_false_on_network_error():
    import httpx

    with patch("app.comms.email._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("timeout", request=MagicMock())
        )
        mock_get_client.return_value = mock_client

        result = await send_email("a@b.com", "A", "S", "B", _make_ngo())

    assert result is False


@pytest.mark.asyncio
async def test_send_email_never_raises():
    """send_email must swallow all exceptions and return False."""
    for status in (400, 401, 403, 404, 429, 500, 502, 503):
        with patch("app.comms.email._get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(status))
            mock_get_client.return_value = mock_client

            result = await send_email("a@b.com", "A", "S", "B", _make_ngo())
            assert isinstance(result, bool), f"Expected bool for status {status}"
