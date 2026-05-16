"""
Platform Helper agent.

Answers questions about using NGO OpsBot itself — the portal, the Telegram bot,
and what each agent can do. Grounds its answers in STAFF_GUIDE.md, fetched
from GitHub and cached in Redis.

This is the agent staff hit when they're confused, not when they need NGO
domain expertise. It preempts support calls by answering "how do I..." and
"what can you do?" questions instantly.

Key design choices:
- Bypasses the 3-layer system prompt (NGO profile layers are irrelevant here)
- Fetches STAFF_GUIDE.md from GitHub; falls back to a bundled copy if unavailable
- Caches the guide in Redis for 1 hour — guide updates propagate without a deploy
- No Google tools — works perfectly for brand-new NGOs before anything is configured
- Always available regardless of which specialist agents are enabled
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

import httpx

from app.agents.base import AgentResponse, BaseAgent
from app.agents.dispatcher import register_agent
from app.core.logging import get_logger
from app.core.metrics import agent_invocations, agent_response_latency, tokens_consumed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ngo import NGO, NGOSettings
    from app.models.staff import Staff

log = get_logger(__name__)

# Redis key and TTL for the cached staff guide
_GUIDE_CACHE_KEY = "platform:staff_guide"
_GUIDE_CACHE_TTL = 3600  # 1 hour

# GitHub raw URL for the staff guide
_GUIDE_URL = (
    "https://raw.githubusercontent.com/shashankkothari/NgoOpsBot/main/STAFF_GUIDE.md"
)

# Bundled fallback — used if GitHub is unreachable.
# Updated manually when major platform changes occur; the live copy is always preferred.
_GUIDE_FALLBACK = """
# NGO OpsBot — Staff Guide (cached copy)

NGO OpsBot gives your NGO AI-powered specialist agents accessible via the staff portal and Telegram.

## Your Agents
- **Fundraising** — donor management, grants, 80G receipts, FCRA compliance
- **Finance** — budgets, expenses, invoices, board reports
- **HR** — staff leave, volunteer coordination, recruitment, offer letters
- **Marketing** — social media content, campaign planning, donor communications
- **Compliance** — FCRA filings, 12A/80G, audit timelines, regulatory deadlines

## Staff Portal
- **Chat** — talk to agents; switch agents from the left sidebar
- **Reminders** — create, snooze, and acknowledge reminders
- **Help & Support** — submit a ticket if something isn't working

## Telegram
- Mention the bot: `@YourBot what grants are due this quarter?`
- `/help` — open a conversation with the Helper
- `/status` — check Google connection and active agents
- `/myaccess` — see which agents you can use

## Tips
- Be specific: name the donor, grant, or staff member you're asking about
- Drafts are never sent automatically — review them in Gmail before sending
- If you get a "not connected" error, ask your admin to link Google from the dashboard

## Need more help?
Submit a support ticket from the Help & Support page.
""".strip()

_HELPER_SYSTEM_PROMPT = """
You are the Platform Helper for NGO OpsBot.

Your only job is to help NGO staff understand and use this platform — the staff portal, \
the Telegram bot, and the specialist agents. You do NOT answer questions about running \
an NGO (donor strategy, FCRA law, accounting, etc.) — those belong to the specialist agents.

The complete staff guide for this platform is provided below. Use it as your primary \
source of truth. Do not invent features or capabilities not described in the guide.

== BEHAVIOUR RULES ==
1. Answer questions about the platform warmly and in plain language. Avoid technical jargon.
2. If the question is about NGO operations (not the platform), redirect:
   "That's a great question for the [Agent Name] agent — switch to it in the sidebar \
or ask your Telegram bot."
3. If you genuinely don't know the answer, say:
   "I'm not sure about that one. Submit a support ticket from the Help & Support page \
and the team will get back to you."
4. Keep answers concise — most questions need 2–4 sentences, not an essay.
5. If a staff member seems frustrated or confused, be patient and offer a concrete next step.
6. When answering about what an agent can do, always include 1–2 example prompts so \
the staff member knows exactly how to ask.

== STAFF GUIDE ==
{guide}
"""


async def _fetch_staff_guide(redis_client) -> str:
    """Fetch the staff guide from Redis cache → GitHub → bundled fallback.

    The 1-hour Redis TTL means guide updates pushed to GitHub propagate
    within an hour without a server restart or deploy.
    """
    # 1. Redis cache
    if redis_client is not None:
        try:
            cached = await redis_client.get(_GUIDE_CACHE_KEY)
            if cached:
                return cached.decode("utf-8")
        except Exception as exc:
            log.warning("helper_guide_cache_read_failed", error=str(exc))

    # 2. GitHub
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            resp = await client.get(
                _GUIDE_URL,
                headers={"Accept": "text/plain"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            guide = resp.text

        # Cache the fetched guide
        if redis_client is not None:
            try:
                await redis_client.setex(_GUIDE_CACHE_KEY, _GUIDE_CACHE_TTL, guide.encode())
            except Exception as exc:
                log.warning("helper_guide_cache_write_failed", error=str(exc))

        log.info("helper_guide_fetched_github", length=len(guide))
        return guide

    except Exception as exc:
        log.warning("helper_guide_github_fetch_failed", error=str(exc))

    # 3. Bundled fallback
    log.info("helper_guide_using_fallback")
    return _GUIDE_FALLBACK


@register_agent
class HelperAgent(BaseAgent):
    """Platform helper — answers questions about using NGO OpsBot.

    Always enabled regardless of which specialist agents are active.
    Accessible via /help on Telegram and the Help button in the staff portal.
    """

    agent_name = "helper"
    tools = []  # no tools — works even before Google is connected

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
        Build a system prompt from the live staff guide and call Claude.

        Bypasses build_system_prompt entirely — the NGO profile layers
        (donor data context, sector-specific guidance) are irrelevant here.
        The only NGO-specific context we inject is which agents are enabled,
        so the helper can give accurate answers about what's available.
        """
        agent_invocations.labels(ngo_slug=ngo.slug, agent_name=self.agent_name).inc()

        # Fetch the guide (fast path: Redis cache)
        guide = await _fetch_staff_guide(redis_client)

        # Inject a brief NGO-specific context so the helper can say
        # "I see Fundraising and Compliance are enabled for your NGO"
        enabled_agents = [s.agent_name for s in ngo_settings if s.is_enabled]
        staff_name = staff.name or "there"
        ngo_context = (
            f"\n== THIS NGO'S CONFIGURATION ==\n"
            f"NGO name: {ngo.name}\n"
            f"Staff member: {staff_name} (role: {staff.role})\n"
            f"Enabled agents: {', '.join(enabled_agents) if enabled_agents else 'none yet'}\n"
            f"Google connected: {'Yes' if ngo.google_refresh_token else 'No — agent integrations (Sheets, Gmail, Calendar) will not work until an admin connects Google from the dashboard'}\n"
        )

        system_prompt = _HELPER_SYSTEM_PROMPT.format(guide=guide) + ngo_context

        # Build message list
        messages: list[dict] = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        # Call Claude (no tool-use loop needed — helper is purely conversational)
        t0 = time.monotonic()
        response_text, input_tokens, output_tokens, cached = await self._call_claude(
            system_prompt=system_prompt,
            messages=messages,
            ngo=ngo,
            staff=staff,
            db=db,
        )
        latency = time.monotonic() - t0

        agent_response_latency.labels(
            ngo_slug=ngo.slug, agent_name=self.agent_name
        ).observe(latency)
        tokens_consumed.labels(ngo_slug=ngo.slug, agent_name=self.agent_name).inc(
            input_tokens + output_tokens
        )

        log.info(
            "helper_agent_response",
            ngo_slug=ngo.slug,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cached,
            latency_ms=round(latency * 1000),
        )

        return AgentResponse(
            text=response_text,
            agent_name=self.agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            language_detected=None,
            cached=cached,
        )
