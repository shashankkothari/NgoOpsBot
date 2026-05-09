"""
BaseAgent — shared invocation logic for all five specialist agents.

Every agent subclass overrides `agent_name` and `_agent_system_prompt`.
The `invoke` method handles the full lifecycle: prompt assembly, Claude
API call with prompt caching, observability, and error surfacing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import anthropic

from app.agents.prompts.loader import build_system_prompt
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import (
    agent_invocations,
    agent_response_latency,
    tokens_consumed,
)
from app.core.security import decrypt_field

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ngo import NGO, NGOSettings
    from app.models.staff import Staff

logger = get_logger(__name__)

# claude-sonnet-4-6 is the default per the task spec (the platform config
# also stores ANTHROPIC_MODEL but agents pin this explicitly for consistency).
_DEFAULT_MODEL = "claude-sonnet-4-6"

# 2 048 output tokens is enough for any Telegram turn; caps runaway spend.
_MAX_TOKENS = 2048


@dataclass
class AgentResponse:
    """Structured output from a single agent turn."""

    text: str
    agent_name: str
    input_tokens: int
    output_tokens: int
    language_detected: Optional[str]
    # True when Anthropic served at least some tokens from cache.
    cached: bool = field(default=False)


class BaseAgent:
    """
    Abstract base for all NGO OpsBot specialist agents.

    Subclasses must set `agent_name` (a short lowercase string matching the
    NGOSettings.agent_name column) and `_agent_system_prompt` (the Layer 1
    specialist extension injected into the system prompt after the platform
    base and NGO profile layers).
    """

    agent_name: str = ""  # e.g. "fundraising"
    _agent_system_prompt: str = ""  # specialist context appended after Layer 3

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
        Full agent turn: build prompt → call Claude → record metrics.

        `conversation_history` items follow the format returned by
        ConversationStore: {"role": "user"|"assistant", "content": str}.
        """
        agent_invocations.labels(
            ngo_slug=ngo.slug, agent_name=self.agent_name
        ).inc()

        # -- 1. Assemble system prompt (3 layers + specialist extension) --
        base_prompt = await build_system_prompt(
            agent_name=self.agent_name,
            ngo=ngo,
            ngo_settings=ngo_settings,
            redis_client=redis_client,
        )
        # Specialist extension is appended last so it can override or narrow
        # the generic guidance from layers 1–3 without touching the cache.
        system_prompt = (
            f"{base_prompt}\n\n{self._agent_system_prompt}".strip()
            if self._agent_system_prompt
            else base_prompt
        )

        # -- 2. Build messages list --
        messages: list[dict] = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        # -- 3. Call Claude --
        t0 = time.monotonic()
        response_text, input_tokens, output_tokens, cached = await self._call_claude(
            system_prompt=system_prompt,
            messages=messages,
            ngo=ngo,
        )
        latency = time.monotonic() - t0

        # -- 4. Record metrics --
        agent_response_latency.labels(
            ngo_slug=ngo.slug, agent_name=self.agent_name
        ).observe(latency)

        tokens_consumed.labels(
            ngo_slug=ngo.slug, agent_name=self.agent_name
        ).inc(input_tokens)
        tokens_consumed.labels(
            ngo_slug=ngo.slug, agent_name=self.agent_name
        ).inc(output_tokens)

        logger.info(
            "claude_api_call",
            ngo_slug=ngo.slug,
            agent_name=self.agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency * 1000),
            cache_hit=cached,
            # Never log message content — privacy invariant.
        )

        return AgentResponse(
            text=response_text,
            agent_name=self.agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            language_detected=None,  # future: detect via langdetect
            cached=cached,
        )

    async def _call_claude(
        self,
        system_prompt: str,
        messages: list[dict],
        ngo: "NGO",
    ) -> tuple[str, int, int, bool]:
        """
        Make a single Claude API call with prompt caching on the system prompt.

        Returns (response_text, input_tokens, output_tokens, cache_hit).

        Key design choices:
        - Uses the NGO's own Anthropic key; falls back to platform key so
          the platform can run without every NGO having their own key.
        - Prompt caching is enabled on the system prompt via cache_control so
          repeated turns in the same conversation reuse the cached prefix.
        - AsyncAnthropic is constructed per-call; the HTTP connection pool
          inside httpx is reused automatically via keep-alive.
        """
        settings = get_settings()

        # Prefer the NGO's own key — cost is billed to them, not the platform.
        try:
            api_key = decrypt_field(ngo.anthropic_api_key)
        except Exception:
            api_key = settings.ANTHROPIC_API_KEY

        client = anthropic.AsyncAnthropic(api_key=api_key)

        # cache_control on the system prompt tells Anthropic to cache this
        # prefix; subsequent turns in the conversation save ~90 % of input
        # token cost for the (large) system prompt.
        system_blocks = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = await client.messages.create(
            model=_DEFAULT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system_blocks,  # type: ignore[arg-type]
            messages=messages,
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text = block.text
                break

        usage = response.usage
        input_tokens: int = usage.input_tokens
        output_tokens: int = usage.output_tokens

        # Anthropic sets cache_read_input_tokens > 0 when the prefix was
        # served from cache; absence or zero means a cache miss (write).
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cached = cache_read > 0

        return response_text, input_tokens, output_tokens, cached
