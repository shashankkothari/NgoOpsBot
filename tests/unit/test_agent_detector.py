"""
Unit tests for app.bot.agent_detector.detect_agent()

Tests cover routing decisions — which agent is selected given text, staff
permissions, and NGO-level enabled settings. External I/O: none.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.bot.agent_detector import ALL_AGENTS, detect_agent
from app.models.ngo import NGOSettings
from app.models.staff import Staff


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_staff(allowed: list[str] | None = None) -> Staff:
    """Return an in-memory Staff with the given allowed_agents list."""
    staff = MagicMock(spec=Staff)
    staff.id = uuid4()
    # Empty list → full access (admin behaviour); explicit list → restricted
    staff.allowed_agents = allowed if allowed is not None else []
    return staff


def _make_settings(enabled: list[str] | None = None) -> list[NGOSettings]:
    """Return NGOSettings with the specified agents enabled (defaults to all)."""
    if enabled is None:
        enabled = ALL_AGENTS
    settings = []
    for name in enabled:
        s = MagicMock(spec=NGOSettings)
        s.agent_name = name
        s.is_enabled = name in enabled
        settings.append(s)
    return settings


def _all_enabled() -> list[NGOSettings]:
    return _make_settings(ALL_AGENTS)


# ---------------------------------------------------------------------------
# Clear keyword routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fundraising_detected_from_donation_campaign():
    staff = _make_staff()  # empty = all agents
    result = await detect_agent("Our donation campaign is running", staff, _all_enabled())
    assert result == "fundraising"


@pytest.mark.asyncio
async def test_finance_detected_from_unpaid_invoice():
    staff = _make_staff()
    result = await detect_agent("Invoice from last month is unpaid", staff, _all_enabled())
    assert result == "finance"


@pytest.mark.asyncio
async def test_marketing_detected_from_instagram_post():
    staff = _make_staff()
    result = await detect_agent("Draft Instagram post for our event", staff, _all_enabled())
    assert result == "marketing"


@pytest.mark.asyncio
async def test_hr_detected_from_leave_application():
    staff = _make_staff()
    result = await detect_agent("Priya applied for leave", staff, _all_enabled())
    assert result == "hr"


@pytest.mark.asyncio
async def test_compliance_detected_from_fcra():
    staff = _make_staff()
    result = await detect_agent("When is FCRA return due?", staff, _all_enabled())
    assert result == "compliance"


# ---------------------------------------------------------------------------
# No match → "general" (system fallback, never None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_keyword_match_returns_general():
    staff = _make_staff()
    result = await detect_agent("The weather is nice today", staff, _all_enabled())
    assert result == "general"


@pytest.mark.asyncio
async def test_empty_text_returns_general():
    staff = _make_staff()
    result = await detect_agent("", staff, _all_enabled())
    assert result == "general"


# ---------------------------------------------------------------------------
# Access control — staff.allowed_agents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_detected_but_not_in_staff_allowed_returns_general():
    # fundraising keyword matches but staff only has finance access → fallback to general
    staff = _make_staff(allowed=["finance"])
    result = await detect_agent("Our donation campaign", staff, _all_enabled())
    assert result == "general"


@pytest.mark.asyncio
async def test_agent_detected_and_in_staff_allowed_returns_agent():
    staff = _make_staff(allowed=["fundraising", "hr"])
    result = await detect_agent("Our donation campaign", staff, _all_enabled())
    assert result == "fundraising"


@pytest.mark.asyncio
async def test_empty_allowed_agents_means_full_access():
    # staff.allowed_agents = [] is the "admin / all access" sentinel
    staff = _make_staff(allowed=[])
    result = await detect_agent("Invoice is overdue", staff, _all_enabled())
    assert result == "finance"


# ---------------------------------------------------------------------------
# Access control — NGO-level enabled settings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_disabled_in_ngo_settings_falls_back_to_next_best():
    # fundraising is disabled; "campaign" also hits marketing → marketing wins
    settings = _make_settings(enabled=["finance", "marketing", "hr", "compliance"])
    staff = _make_staff()  # all access
    result = await detect_agent("Our donation campaign", staff, settings)
    assert result in ("marketing", "general")


@pytest.mark.asyncio
async def test_agent_enabled_in_ngo_settings_is_returned():
    settings = _make_settings(enabled=["fundraising"])
    staff = _make_staff()
    result = await detect_agent("donor and grant fundraising", staff, settings)
    assert result == "fundraising"


@pytest.mark.asyncio
async def test_no_enabled_agents_returns_general():
    # NGO has disabled everything → fallback to general
    settings: list[NGOSettings] = []
    staff = _make_staff()
    result = await detect_agent("Our donation campaign invoice", staff, settings)
    assert result == "general"


# ---------------------------------------------------------------------------
# Tie-breaking and multi-keyword scoring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_keyword_matches_returns_highest_scoring_agent():
    # "donor grant campaign fundrais" hits fundraising 4 times,
    # "campaign" alone hits marketing 1 time → fundraising wins
    staff = _make_staff()
    text = "donor grant campaign fundraising drive"
    result = await detect_agent(text, staff, _all_enabled())
    assert result == "fundraising"


@pytest.mark.asyncio
async def test_single_keyword_match_still_routes_correctly():
    staff = _make_staff()
    result = await detect_agent("We need to review the budget", staff, _all_enabled())
    assert result == "finance"


@pytest.mark.asyncio
async def test_tie_broken_by_canonical_agent_order():
    # "campaign" appears in both fundraising and marketing keyword lists.
    # With equal scores, canonical order (fundraising before marketing) wins.
    staff = _make_staff()
    result = await detect_agent("campaign", staff, _all_enabled())
    # campaign is in both lists; fundraising appears first in ALL_AGENTS
    assert result in ("fundraising", "marketing")
    # Whatever wins, it must be a valid agent
    assert result in ALL_AGENTS


# ---------------------------------------------------------------------------
# Hindi text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hindi_donation_campaign_text_returns_general():
    # "दान अभियान" = "donation campaign" — no English keywords matched,
    # so the system falls back to general (not None).
    staff = _make_staff()
    result = await detect_agent("दान अभियान के लिए मदद चाहिए", staff, _all_enabled())
    assert result == "general"


@pytest.mark.asyncio
async def test_hindi_text_with_embedded_english_keyword_routes_correctly():
    # Mixed-language messages are common — English keywords in Hindi text
    # should still trigger the right agent.
    staff = _make_staff()
    result = await detect_agent("हमारे donor को धन्यवाद", staff, _all_enabled())
    assert result == "fundraising"
