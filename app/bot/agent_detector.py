"""
Keyword-based agent routing — determines which agent should handle a message.

Keyword-first routing avoids an extra Claude API call for every message.
We pay the cost of an LLM routing call only when keyword matching is
ambiguous or absent, and only in a future v2 iteration.
"""

from __future__ import annotations

from typing import Optional

import structlog

from app.core.logging import get_logger
from app.models.ngo import NGOSettings
from app.models.staff import Staff

log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Keywords are lowercase substrings — we match with `in text.lower()`
# Each list is ordered by specificity; more specific terms are listed first
# so that scoring rewards precise matches equally (all weighted 1 point each).
AGENT_KEYWORDS: dict[str, list[str]] = {
    # "general" is checked first — explicit help requests go straight to the orchestrator
    # rather than being misrouted to a specialist via keyword overlap.
    "general": [
        "help", "/help", "what can you do", "what agents", "list agents",
        "who are you", "how do you work", "what do you do",
    ],
    "fundraising": [
        "donor", "donation", "grant", "fundrais", "campaign", "pledge",
        "crowdfund", "benefactor", "endowment", "charity drive",
    ],
    "finance": [
        "budget", "expense", "invoice", "payment", "account", "financial",
        "spend", "reimburse", "ledger", "receipt", "cash flow", "balance sheet",
    ],
    "marketing": [
        "social", "post", "content", "campaign", "audience", "brand", "publish",
        "newsletter", "outreach", "engagement", "awareness", "press release",
    ],
    "hr": [
        "staff", "volunteer", "leave", "salary", "onboard", "recruit",
        "attendance", "payroll", "hiring", "interview", "performance review",
    ],
    "compliance": [
        "legal", "regulation", "fcra", "report", "audit", "compliance",
        "policy", "80g", "12a", "csr", "statutory", "filing",
    ],
}

# All known agent names in canonical order (general excluded — it's always the fallback)
ALL_AGENTS = [a for a in AGENT_KEYWORDS if a != "general"]


def _score_text(text: str, agent: str) -> int:
    """Count how many keywords for `agent` appear in `text`."""
    lower = text.lower()
    return sum(1 for kw in AGENT_KEYWORDS[agent] if kw in lower)


def _enabled_permitted_agents(
    staff: Staff,
    ngo_settings: list[NGOSettings],
) -> set[str]:
    """Intersection of: agents enabled for the NGO AND permitted for this staff member."""
    enabled_for_ngo = {s.agent_name for s in ngo_settings if s.is_enabled}
    # allowed_agents=[] means all-access (e.g. admin); treat empty list as full access
    if staff.allowed_agents:
        permitted = set(staff.allowed_agents)
    else:
        permitted = set(ALL_AGENTS)
    return enabled_for_ngo & permitted


async def detect_agent(
    text: str,
    staff: Staff,
    ngo_settings: list[NGOSettings],
) -> Optional[str]:
    """
    Return the best-matching agent name.

    "general" is returned as the explicit fallback when no specialist keyword
    matches — the GeneralAgent then uses Haiku to classify intent and routes
    to the right specialist transparently (two-phase orchestration).

    Returns None only when no agents at all are enabled/permitted for this staff
    member, which should prompt a configuration error message to the user.
    """
    candidates = _enabled_permitted_agents(staff, ngo_settings)

    # "general" is a system agent — always available regardless of NGO settings
    has_any_agent = bool(candidates) or True  # general is always present

    # Check for explicit help/navigation keywords first — highest priority
    lower = text.lower()
    for kw in AGENT_KEYWORDS["general"]:
        if kw in lower:
            log.debug("agent_detected_general_keyword", keyword=kw, staff_id=str(staff.id))
            return "general"

    if not candidates:
        log.debug(
            "agent_detect_no_candidates",
            staff_id=str(staff.id),
            allowed_agents=staff.allowed_agents,
        )
        # Still route to general — it can explain what's available
        return "general"

    scores: dict[str, int] = {
        agent: _score_text(text, agent)
        for agent in candidates
    }

    # Filter to agents that scored at least one keyword match
    matched = {agent: score for agent, score in scores.items() if score > 0}
    if not matched:
        log.debug(
            "agent_detect_no_keyword_match_routing_to_general",
            staff_id=str(staff.id),
            candidates=list(candidates),
        )
        # No keyword match → orchestrator will classify with Haiku
        return "general"

    # Pick the highest scorer; ties broken by canonical order for determinism
    best_agent = max(matched, key=lambda a: (matched[a], -ALL_AGENTS.index(a)))
    log.debug(
        "agent_detected",
        agent=best_agent,
        score=matched[best_agent],
        all_scores=matched,
        staff_id=str(staff.id),
    )
    return best_agent
