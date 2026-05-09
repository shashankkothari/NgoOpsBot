"""
Text message handler — the core agent dispatch path.

This module is the authoritative place where a user message turns into an
agent invocation. Every observability event for agent interactions is emitted
from here so the dashboard can accurately count invocations and latency.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dispatcher import dispatch as dispatch_to_agent
from app.bot.agent_detector import detect_agent
from app.bot.conversation_store import get_conversation_history, save_conversation_turn
from app.bot.ngo_bot_registry import bot_registry
from app.bot.update_parser import ParsedUpdate
from app.core.logging import get_logger
from app.core.metrics import (
    agent_invocations,
    agent_response_latency,
    messages_processed,
)
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff

log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Message sent while Claude processes — keeps staff from thinking the bot is dead
_THINKING_MESSAGE = "🤔 Thinking..."

# Sent when the message is addressed to the bot but no agent can be determined
_CLARIFICATION_MESSAGE = (
    "I'm not sure which area you need help with. Could you be more specific? "
    "For example: 'Help with donor reporting' or 'Budget spreadsheet question'.\n"
    "Use /help to see available agents."
)

# Max chars per Telegram message — split longer responses
_TELEGRAM_MAX_LENGTH = 4096


async def handle_text_message(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Staff,
    ngo_settings: list[NGOSettings],
    db: AsyncSession,
) -> None:
    """
    Full pipeline: detect agent → check permission → invoke → persist → reply.
    """
    ngo_slug = ngo.slug
    text = parsed.text or ""

    bound_log = log.bind(
        ngo_slug=ngo_slug,
        staff_id=str(staff.id),
        telegram_user_id=parsed.telegram_user_id,
        message_id=parsed.message_id,
    )

    # --- 1. Detect agent -------------------------------------------------------
    agent_name = await detect_agent(text, staff, ngo_settings)

    if agent_name is None:
        bound_log.info(
            "message_ignored_no_agent_detected",
            text_length=len(text),
            # Never log text content — it may contain sensitive NGO information
        )
        await bot_registry.send_message(
            ngo_slug, parsed.chat_id, _CLARIFICATION_MESSAGE
        )
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name="none", message_type="text"
        ).inc()
        return

    bound_log = bound_log.bind(agent_name=agent_name)

    # --- 2. Check staff permission --------------------------------------------
    # "general" is the orchestrator — always permitted, no NGOSettings row.
    # For specialists: allowed_agents=[] means all-access (admin role).
    if agent_name != "general":
        if staff.allowed_agents and agent_name not in staff.allowed_agents:
            bound_log.info(
                "message_ignored_agent_not_permitted",
                allowed_agents=staff.allowed_agents,
            )
            await bot_registry.send_message(
                ngo_slug,
                parsed.chat_id,
                f"You don't have access to the <b>{agent_name.capitalize()}</b> agent. "
                "Contact your admin to request access.",
                parse_mode="HTML",
            )
            messages_processed.labels(
                ngo_slug=ngo_slug, agent_name=agent_name, message_type="text"
            ).inc()
            return

        # Belt-and-suspenders: confirm agent is enabled for this NGO
        enabled_agents = {s.agent_name for s in ngo_settings if s.is_enabled}
        if agent_name not in enabled_agents:
            bound_log.info("message_ignored_agent_disabled_for_ngo")
            messages_processed.labels(
                ngo_slug=ngo_slug, agent_name=agent_name, message_type="text"
            ).inc()
            return

    # --- 3. Typing indicator ---------------------------------------------------
    await bot_registry.send_typing_action(ngo_slug, parsed.chat_id)

    # --- 4. Load conversation history for context window ----------------------
    history = await get_conversation_history(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=agent_name,
        db=db,
    )

    # --- 5. Invoke agent -------------------------------------------------------
    agent_invocations.labels(ngo_slug=ngo_slug, agent_name=agent_name).inc()
    bound_log.info("agent_invocation_start", history_turns=len(history))

    start_time = time.monotonic()
    try:
        reply_text, tokens_used, language_detected, actual_agent_name = await _call_agent(
            ngo=ngo,
            agent_name=agent_name,
            staff=staff,
            text=text,
            history=history,
            ngo_settings=ngo_settings,
            db=db,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start_time
        bound_log.error(
            "agent_invocation_failed",
            error=str(exc),
            elapsed_seconds=round(elapsed, 3),
            exc_info=True,
        )
        await bot_registry.send_message(
            ngo_slug,
            parsed.chat_id,
            "Sorry, I ran into an error. Please try again in a moment.",
        )
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name=agent_name, message_type="text"
        ).inc()
        return

    elapsed = time.monotonic() - start_time
    # Use actual_agent_name for metrics/persistence — when the orchestrator routes
    # to a specialist, actual_agent_name is the specialist's name (e.g. "compliance"),
    # not "general". This ensures the ConversationThread is created under the
    # specialist so follow-up messages route directly there.
    agent_response_latency.labels(ngo_slug=ngo_slug, agent_name=actual_agent_name).observe(elapsed)
    bound_log.info(
        "agent_invocation_complete",
        elapsed_seconds=round(elapsed, 3),
        tokens_used=tokens_used,
        language_detected=language_detected,
        actual_agent=actual_agent_name,
    )

    # --- 6. Send reply --------------------------------------------------------
    await _send_chunked(ngo_slug, parsed.chat_id, reply_text, parsed.message_id)

    # --- 7 & 8. Persist both turns + thread stats -----------------------------
    # Save under actual_agent_name so follow-ups route to the specialist directly.
    await save_conversation_turn(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=actual_agent_name,
        role="user",
        content=text,
        telegram_message_id=parsed.message_id,
        chat_id=parsed.chat_id,
        tokens_used=None,
        language_detected=language_detected,
        db=db,
    )
    await save_conversation_turn(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=actual_agent_name,
        role="assistant",
        content=reply_text,
        telegram_message_id=-1,
        chat_id=parsed.chat_id,
        tokens_used=tokens_used,
        language_detected=language_detected,
        db=db,
    )

    # --- 9. Metrics -----------------------------------------------------------
    messages_processed.labels(
        ngo_slug=ngo_slug, agent_name=actual_agent_name, message_type="text"
    ).inc()


async def _call_agent(
    ngo: NGO,
    agent_name: str,
    staff: Staff,
    text: str,
    history: list[dict[str, str]],
    ngo_settings: list[NGOSettings],
    db: AsyncSession,
) -> tuple[str, Optional[int], Optional[str], str]:
    """
    Dispatch to the correct agent and return
    (reply_text, tokens_used, language_detected, actual_agent_name).

    actual_agent_name differs from agent_name when the GeneralAgent transparently
    routes to a specialist — the returned agent_name is the specialist's, so the
    caller can persist the ConversationThread under the right name.
    """
    from app.core.cache import get_redis
    redis = await get_redis()

    response = await dispatch_to_agent(
        agent_name=agent_name,
        user_message=text,
        ngo=ngo,
        staff=staff,
        conversation_history=history,
        ngo_settings=ngo_settings,
        db=db,
        redis_client=redis,
    )
    return (
        response.text,
        response.input_tokens + response.output_tokens,
        response.language_detected,
        response.agent_name,
    )


async def _send_chunked(
    ngo_slug: str,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    Telegram caps messages at 4096 chars; split long replies into chunks.

    We split on newlines when possible to avoid cutting mid-word.
    reply_to_message_id is only set for the first chunk so the thread is clear.
    """
    if len(text) <= _TELEGRAM_MAX_LENGTH:
        await bot_registry.send_message(
            ngo_slug,
            chat_id,
            text,
            parse_mode="HTML",
            reply_to_message_id=reply_to_message_id,
        )
        return

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= _TELEGRAM_MAX_LENGTH:
            chunks.append(remaining)
            break
        # Try to split at a newline within the allowed window
        split_at = remaining.rfind("\n", 0, _TELEGRAM_MAX_LENGTH)
        if split_at == -1:
            split_at = _TELEGRAM_MAX_LENGTH
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    for i, chunk in enumerate(chunks):
        await bot_registry.send_message(
            ngo_slug,
            chat_id,
            chunk,
            parse_mode="HTML",
            # Only thread the first chunk; subsequent chunks should flow naturally
            reply_to_message_id=reply_to_message_id if i == 0 else None,
        )
