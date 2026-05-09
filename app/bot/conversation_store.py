"""
Conversation persistence — read history for context window and write new turns.

Thread lifecycle: a new ConversationThread is started when the previous one has
been idle for >30 minutes. This mirrors a natural "session" boundary and keeps
context windows focused on the current task rather than yesterday's discussion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import tokens_consumed
from app.models.conversation import Conversation, ConversationThread

log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Gap longer than this triggers a new thread rather than continuing the old one
_THREAD_IDLE_TIMEOUT = timedelta(minutes=30)
# Hard cap on context turns to bound token usage; older turns are silently dropped
_DEFAULT_MAX_TURNS = 10


async def _get_or_create_thread(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    agent_name: str,
    db: AsyncSession,
) -> ConversationThread:
    """Return the active thread for this staff-agent pair, or start a new one."""
    now = datetime.now(timezone.utc)
    cutoff = now - _THREAD_IDLE_TIMEOUT

    result = await db.execute(
        select(ConversationThread)
        .where(
            ConversationThread.ngo_id == ngo_id,
            ConversationThread.staff_id == staff_id,
            ConversationThread.agent_name == agent_name,
            ConversationThread.is_active.is_(True),
            # last_activity_at is tz-aware (server_default=func.now())
            ConversationThread.last_activity_at >= cutoff,
        )
        .order_by(ConversationThread.last_activity_at.desc())
        .limit(1)
    )
    thread = result.scalar_one_or_none()

    if thread is None:
        thread = ConversationThread(
            id=uuid.uuid4(),
            ngo_id=ngo_id,
            staff_id=staff_id,
            agent_name=agent_name,
            started_at=now,
            last_activity_at=now,
            message_count=0,
            is_active=True,
        )
        db.add(thread)
        # Flush so the thread has a DB-assigned PK before we reference it
        await db.flush()
        log.info(
            "conversation_thread_started",
            thread_id=str(thread.id),
            ngo_id=str(ngo_id),
            staff_id=str(staff_id),
            agent_name=agent_name,
        )

    return thread


async def get_conversation_history(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    agent_name: str,
    db: AsyncSession,
    max_turns: int = _DEFAULT_MAX_TURNS,
) -> list[dict[str, str]]:
    """
    Return the last `max_turns` messages as Claude-compatible role/content dicts.

    We fetch max_turns*2 rows (each turn = user + assistant) ordered desc,
    then reverse to give chronological order for the LLM context window.
    """
    thread = await _get_or_create_thread(ngo_id, staff_id, agent_name, db)

    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.ngo_id == ngo_id,
            Conversation.staff_id == staff_id,
            Conversation.agent_name == agent_name,
        )
        # Fetch most-recent rows first, then reverse below for chronological order
        .order_by(Conversation.created_at.desc())
        # max_turns pairs of user+assistant = 2*max_turns rows
        .limit(max_turns * 2)
    )
    rows = result.scalars().all()

    # Reverse to chronological order for the LLM prompt
    history = [{"role": row.role, "content": row.content} for row in reversed(rows)]

    log.debug(
        "conversation_history_loaded",
        thread_id=str(thread.id),
        turns=len(history),
        ngo_id=str(ngo_id),
        agent_name=agent_name,
    )
    return history


async def save_conversation_turn(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    agent_name: str,
    role: str,
    content: str,
    telegram_message_id: int,
    chat_id: int,
    tokens_used: Optional[int],
    language_detected: Optional[str],
    db: AsyncSession,
) -> None:
    """Persist one message turn and update thread stats atomically."""
    thread = await _get_or_create_thread(ngo_id, staff_id, agent_name, db)

    conv = Conversation(
        id=uuid.uuid4(),
        ngo_id=ngo_id,
        staff_id=staff_id,
        agent_name=agent_name,
        role=role,
        content=content,
        telegram_message_id=telegram_message_id,
        telegram_chat_id=chat_id,
        tokens_used=tokens_used,
        language_detected=language_detected,
    )
    db.add(conv)

    # Update thread metadata — last_activity_at uses onupdate on the column, but
    # we set it explicitly here so the 30-minute window is always accurate.
    thread.last_activity_at = datetime.now(timezone.utc)
    thread.message_count = (thread.message_count or 0) + 1

    await db.flush()

    if tokens_used:
        # ngo_slug unavailable here without an extra join; use ngo_id as fallback label
        tokens_consumed.labels(ngo_slug=str(ngo_id), agent_name=agent_name).inc(tokens_used)

    log.debug(
        "conversation_turn_saved",
        conversation_id=str(conv.id),
        thread_id=str(thread.id),
        role=role,
        agent_name=agent_name,
        # Never log content — it may contain PII or confidential NGO data
        tokens_used=tokens_used,
        language_detected=language_detected,
    )
