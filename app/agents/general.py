"""
General / Orchestrator agent — intelligent routing layer.

Two-phase flow on first contact:
  Phase 1 (Haiku, ~100ms): classify which specialist should own the message.
  Phase 2 (Sonnet): invoke that specialist transparently and return its response.

The ConversationThread is saved under the specialist's agent_name, so all
follow-up messages in the 30-minute window go directly to the specialist —
the orchestrator is never invoked again for that session.

When no specialist is appropriate (help requests, greetings, unclear intent),
this agent answers directly using its cross-domain NGO knowledge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import anthropic

from app.agents.base import AgentResponse, BaseAgent
from app.agents.dispatcher import register_agent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_field

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ngo import NGO, NGOSettings
    from app.models.staff import Staff

logger = get_logger(__name__)

# Haiku is used for intent classification only — fast and cheap.
# The specialist (Sonnet) handles the actual response.
_CLASSIFICATION_MODEL = "claude-haiku-4-5-20251001"

_AGENT_DOMAINS = {
    "fundraising": "donors, grants, campaigns, pledges, 80G receipts, CSR, FCRA, donor comms",
    "finance": "budgets, expenses, invoices, financial reports, TDS, grant utilisation, audit",
    "marketing": "social media posts, content calendars, newsletters, press releases, impact stories",
    "hr": "staff leave, volunteers, recruitment, onboarding, payroll info, performance reviews",
    "compliance": "legal filings, FCRA, 12A/80G registration, ITR-7, statutory reports, audits",
}

# Shown when no specialist agent is available or the query is truly general
_DIRECT_ANSWER_PROMPT = """
You are the General Assistant for this NGO's operations bot.

You help staff with two things:
1. Navigating the bot — explaining what each specialist agent does and how to phrase questions.
2. Cross-domain queries or questions that don't fit neatly into one specialist area.

Available specialist agents and their domains:
- fundraising: donors, grants, campaigns, 80G receipts, CSR, FCRA, donor comms
- finance: budgets, expenses, invoices, financial reports, TDS, grant utilisation
- marketing: social media posts, content calendars, newsletters, press releases
- hr: staff leave, volunteers, recruitment, onboarding, payroll info
- compliance: FCRA, 12A/80G, ITR-7, statutory filings, audits

When answering help queries, give a concrete example of how to phrase the request:
  "For grant tracking, try: '@bot which grants have reporting due this quarter?'"

Be concise, warm, and action-oriented. Under 300 words unless more detail is asked for.
"""


@register_agent
class GeneralAgent(BaseAgent):
    agent_name = "general"
    _agent_system_prompt = _DIRECT_ANSWER_PROMPT

    async def invoke(
        self,
        user_message: str,
        ngo: "NGO",
        staff: "Staff",
        conversation_history: list[dict],
        ngo_settings: list["NGOSettings"],
        db: "AsyncSession",
        redis_client,
    ) -> AgentResponse:
        """
        Phase 1: classify with Haiku.
        Phase 2: dispatch to specialist (if classified) or answer directly.
        """
        specialist = await self._classify_intent(
            user_message=user_message,
            ngo=ngo,
            ngo_settings=ngo_settings,
            staff=staff,
        )

        if specialist and specialist != "general":
            logger.info(
                "orchestrator_routing_to_specialist",
                ngo_slug=ngo.slug,
                staff_id=str(staff.id),
                specialist=specialist,
            )
            # Transparent handoff — the returned response carries agent_name=specialist
            # so the caller saves the thread under the specialist's name.
            from app.agents.dispatcher import (
                AgentNotEnabledError,
                AgentNotPermittedError,
                dispatch,
            )
            try:
                return await dispatch(
                    agent_name=specialist,
                    user_message=user_message,
                    ngo=ngo,
                    staff=staff,
                    conversation_history=conversation_history,
                    ngo_settings=ngo_settings,
                    db=db,
                    redis_client=redis_client,
                )
            except (AgentNotEnabledError, AgentNotPermittedError) as exc:
                # Specialist unavailable for this staff/NGO — fall through to direct answer
                logger.info(
                    "orchestrator_specialist_unavailable",
                    specialist=specialist,
                    reason=str(exc),
                )

        # Direct answer: help queries, greetings, or specialist unavailable
        return await super().invoke(
            user_message=user_message,
            ngo=ngo,
            staff=staff,
            conversation_history=conversation_history,
            ngo_settings=ngo_settings,
            db=db,
            redis_client=redis_client,
        )

    async def _classify_intent(
        self,
        user_message: str,
        ngo: "NGO",
        ngo_settings: list["NGOSettings"],
        staff: "Staff",
    ) -> Optional[str]:
        """
        Single Haiku call that returns the best specialist name or 'general'.

        Only specialists that are enabled for the NGO AND permitted for this
        staff member are offered as candidates.
        """
        settings = get_settings()
        try:
            api_key = decrypt_field(ngo.anthropic_api_key)
        except Exception:
            api_key = settings.ANTHROPIC_API_KEY

        # Build candidate list respecting NGO settings and staff permissions
        enabled = {s.agent_name for s in ngo_settings if s.is_enabled}
        if staff.allowed_agents:
            enabled &= set(staff.allowed_agents)
        candidates = sorted(enabled & set(_AGENT_DOMAINS.keys()))

        if not candidates:
            return "general"

        domain_lines = "\n".join(
            f"- {name}: {_AGENT_DOMAINS[name]}"
            for name in candidates
        )
        classification_prompt = (
            f"Route this NGO staff message to the best agent.\n\n"
            f"Available agents:\n{domain_lines}\n- general: help, navigation, unclear intent, greetings\n\n"
            f"Message: \"{user_message}\"\n\n"
            f"Reply with exactly one agent name from the list. Nothing else."
        )

        client = anthropic.AsyncAnthropic(api_key=api_key)
        try:
            response = await client.messages.create(
                model=_CLASSIFICATION_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": classification_prompt}],
            )
            result = response.content[0].text.strip().lower()
            valid = set(candidates) | {"general"}
            return result if result in valid else "general"
        except Exception as exc:
            logger.warning("orchestrator_classification_failed", error=str(exc))
            return "general"
