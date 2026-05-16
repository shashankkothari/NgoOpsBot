"""
BaseAgent — shared invocation logic for all five specialist agents.

Every agent subclass overrides `agent_name` and `_agent_system_prompt`.
The `invoke` method handles the full lifecycle: prompt assembly, Claude
API call with prompt caching, tool-use loop, observability, and error surfacing.

Tool-use loop:
  When an agent declares `tools` (a list of tool names from definitions.py),
  _call_claude runs a loop that:
    1. Calls Claude with the tool definitions.
    2. If stop_reason == "tool_use", executes each requested tool.
    3. Appends tool results to the message list and calls Claude again.
    4. Repeats until stop_reason == "end_turn" or _MAX_TOOL_ITERATIONS is reached.
  Token counts are accumulated across all iterations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

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

# Maximum tool-use iterations per turn to prevent infinite loops.
# A well-behaved agent rarely needs more than 3–4 round trips.
_MAX_TOOL_ITERATIONS = 10


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

    Optionally override `tools` with a list of tool names from
    app.agents.tools.definitions.ALL_TOOL_DEFINITIONS to enable tool use.
    An empty list (the default) means conversational-only, no tools.
    """

    agent_name: str = ""  # e.g. "fundraising"
    _agent_system_prompt: str = ""  # specialist context appended after Layer 3
    tools: list[str] = []  # tool names; empty = conversational only

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

        # -- 3. Call Claude (with tool-use loop if the agent declares tools) --
        t0 = time.monotonic()
        response_text, input_tokens, output_tokens, cached = await self._call_claude(
            system_prompt=system_prompt,
            messages=messages,
            ngo=ngo,
            staff=staff,
            db=db,
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
        staff: "Optional[Staff]" = None,
        db: "Optional[AsyncSession]" = None,
    ) -> tuple[str, int, int, bool]:
        """
        Call Claude with a tool-use loop, returning the final text response.

        Returns (response_text, total_input_tokens, total_output_tokens, cache_hit).

        Key design choices:
        - Uses the NGO's own Anthropic key; falls back to platform key so
          the platform can run without every NGO having their own key.
        - Prompt caching is enabled on the system prompt via cache_control so
          repeated turns in the same conversation reuse the cached prefix.
        - If the agent declares `tools`, the Anthropic call includes tool
          definitions and the loop handles tool_use → execute → continue until
          the model reaches end_turn or _MAX_TOOL_ITERATIONS is exhausted.
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
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # Resolve tool definitions for this agent
        from app.agents.tools.definitions import AGENT_TOOLS, get_tool_definitions
        from app.agents.tools.executor import ToolContext, execute_tool

        agent_tool_names = AGENT_TOOLS.get(self.agent_name, getattr(self, "tools", []))
        tool_definitions = get_tool_definitions(agent_tool_names)

        # Build the tool context (used if any tool calls happen)
        tool_context = ToolContext(ngo=ngo, staff=staff, db=db)

        # Working message list — grows with tool turns but never mutates the
        # caller's list (conversation history must stay clean)
        working_messages: list[dict] = list(messages)

        total_input_tokens = 0
        total_output_tokens = 0
        first_call = True
        cached = False
        response_text = ""

        try:
            for _iteration in range(_MAX_TOOL_ITERATIONS):
                # Build the API call kwargs
                call_kwargs: dict[str, Any] = dict(
                    model=_DEFAULT_MODEL,
                    max_tokens=_MAX_TOKENS,
                    system=system_blocks,  # type: ignore[arg-type]
                    messages=working_messages,
                )
                if tool_definitions:
                    call_kwargs["tools"] = tool_definitions  # type: ignore[assignment]

                response = await client.messages.create(**call_kwargs)

                usage = response.usage
                total_input_tokens += usage.input_tokens
                total_output_tokens += usage.output_tokens

                # Cache hit is meaningful only on the first call (system prompt cache)
                if first_call:
                    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                    cached = cache_read > 0
                    first_call = False

                # --- end_turn: extract text and finish ---
                if response.stop_reason != "tool_use":
                    for block in response.content:
                        if block.type == "text":
                            response_text = block.text
                            break
                    break

                # --- tool_use: execute tools and continue ---
                # Serialise the assistant turn (may contain text + tool_use blocks)
                assistant_content: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                working_messages.append({"role": "assistant", "content": assistant_content})

                # Execute each tool call and collect results
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    logger.info(
                        "agent_tool_call",
                        agent_name=self.agent_name,
                        ngo_slug=ngo.slug,
                        tool_name=block.name,
                        iteration=_iteration,
                    )
                    result_str = await execute_tool(block.name, block.input, tool_context)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

                working_messages.append({"role": "user", "content": tool_results})

            else:
                # Reached _MAX_TOOL_ITERATIONS without end_turn
                logger.warning(
                    "agent_tool_iteration_limit",
                    agent_name=self.agent_name,
                    ngo_slug=ngo.slug,
                    limit=_MAX_TOOL_ITERATIONS,
                )
                if not response_text:
                    response_text = (
                        "I reached the maximum number of tool calls for this turn. "
                        "Please try breaking your request into smaller steps."
                    )

        except anthropic.AuthenticationError as exc:
            raise ValueError(
                "Anthropic API key is invalid or missing. "
                "Update the key in the NGO settings in the admin dashboard."
            ) from exc
        except anthropic.APIStatusError as exc:
            raise ValueError(f"Anthropic API error: {exc.message}") from exc

        return response_text, total_input_tokens, total_output_tokens, cached
