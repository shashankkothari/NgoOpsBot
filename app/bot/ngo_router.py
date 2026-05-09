"""
Core update router — the single entry point for all Telegram updates per NGO.

All non-fatal errors are caught here and logged. We never propagate exceptions
to the webhook handler because an unhandled exception would cause the webhook
to return a 500, triggering Telegram's exponential-backoff retry storm.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ngo_bot_registry import bot_registry
from app.bot.update_parser import ParsedUpdate, parse_update
from app.core.logging import get_logger
from app.core.metrics import messages_processed
from app.core.security import decrypt_field
from app.models.conversation import ConversationThread
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff

log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Redis TTL for NGO config — config rarely changes, 5 minutes gives a fresh-enough view
_NGO_CACHE_TTL_SECONDS = 300
_NGO_CACHE_PREFIX = "ngo:config:"


async def route_update(
    ngo_slug: str,
    update_data: dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Main entry point. Implements the 10-step flow described in the module docstring.
    Swallows all exceptions — callers must always get a clean return.
    """
    bound_log = log.bind(
        ngo_slug=ngo_slug,
        update_id=update_data.get("update_id"),
    )

    try:
        await _route(ngo_slug, update_data, db, bound_log)
    except Exception as exc:
        bound_log.error(
            "route_update_unhandled_exception",
            error=str(exc),
            exc_info=True,
        )


async def _route(
    ngo_slug: str,
    update_data: dict[str, Any],
    db: AsyncSession,
    bound_log: structlog.stdlib.BoundLogger,
) -> None:
    # --- Step 1: Load NGO (with Redis cache) ---------------------------------
    ngo, ngo_settings = await _load_ngo_cached(ngo_slug, db, bound_log)
    if ngo is None:
        bound_log.error("route_ngo_not_found")
        return

    if not ngo.is_active:
        bound_log.info("route_ngo_inactive")
        return

    # --- Handle callback_query (inline keyboard) separately ------------------
    # Callbacks don't have a 'message' key, so parse_update would return None
    if "callback_query" in update_data:
        from app.bot.handlers.callback_handler import handle_callback_query

        await handle_callback_query(update_data=update_data, ngo=ngo, db=db)
        return

    # --- Step 2: Parse the update --------------------------------------------
    bot = await bot_registry.get_bot(ngo_slug, ngo.telegram_bot_token)
    bot_info = await bot.get_me()
    bot_username: str = bot_info.username or ""

    parsed: Optional[ParsedUpdate] = parse_update(update_data, bot_username)
    if parsed is None:
        bound_log.debug("route_update_not_parseable")
        return

    bound_log = bound_log.bind(
        chat_id=parsed.chat_id,
        telegram_user_id=parsed.telegram_user_id,
        message_type="command" if parsed.is_command else ("voice" if parsed.voice else "text"),
    )

    # --- Step 3: Group chat enforcement --------------------------------------
    # We don't respond to DMs — the entire workflow is designed around group ops
    if not parsed.is_group_message:
        bound_log.info("route_ignored_not_group_message")
        return

    # Only respond in the group this NGO registered — prevents cross-contamination
    # if the bot is accidentally added to a different group
    if ngo.telegram_group_chat_id and parsed.chat_id != ngo.telegram_group_chat_id:
        bound_log.info(
            "route_ignored_wrong_group",
            expected_group=ngo.telegram_group_chat_id,
            actual_group=parsed.chat_id,
        )
        return

    # First message from any group — record the group chat ID for future enforcement
    if ngo.telegram_group_chat_id is None:
        bound_log.info("route_recording_group_chat_id", chat_id=parsed.chat_id)
        ngo.telegram_group_chat_id = parsed.chat_id
        await db.flush()

    # --- Step 4: Identify staff member ----------------------------------------
    staff_result = await db.execute(
        select(Staff).where(
            Staff.ngo_id == ngo.id,
            Staff.telegram_user_id == parsed.telegram_user_id,
            Staff.is_active.is_(True),
        )
    )
    staff: Optional[Staff] = staff_result.scalar_one_or_none()

    if staff is None and not parsed.is_command:
        # Non-command from unknown user — log for audit, don't respond
        bound_log.info(
            "route_ignored_unknown_staff",
            message_type="command" if parsed.is_command else "text",
        )
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name="none", message_type="unknown"
        ).inc()
        return

    # --- Step 5: Handle slash commands ----------------------------------------
    if parsed.is_command:
        from app.bot.handlers.command_handler import handle_command

        await handle_command(
            parsed=parsed,
            ngo=ngo,
            staff=staff,
            ngo_settings=ngo_settings,
            db=db,
        )
        return

    # Guaranteed non-None beyond this point: unknown staff was already rejected above
    assert staff is not None  # noqa: S101

    bound_log = bound_log.bind(staff_id=str(staff.id))

    # --- Step 6: @mention / reply-to-bot gate --------------------------------
    # In group chats the bot receives EVERY message. We only respond when
    # explicitly addressed OR when the staff member has an active conversation
    # thread (last activity within 30 min) — so follow-up messages in an ongoing
    # session don't require re-mentioning the bot each time.
    if not parsed.bot_mentioned and not parsed.reply_to_bot:
        active_thread = await _find_active_thread(ngo.id, staff.id, db)
        if active_thread is None:
            bound_log.debug(
                "route_ignored_not_addressed",
                bot_mentioned=parsed.bot_mentioned,
                reply_to_bot=parsed.reply_to_bot,
            )
            return
        bound_log.debug(
            "route_continuing_active_thread",
            thread_id=str(active_thread.id),
            agent_name=active_thread.agent_name,
        )

    # --- Steps 7–10: Dispatch to content handler ------------------------------
    if parsed.voice:
        from app.bot.handlers.voice_handler import handle_voice_message

        await handle_voice_message(
            parsed=parsed,
            ngo=ngo,
            staff=staff,
            ngo_settings=ngo_settings,
            db=db,
        )
    else:
        from app.bot.handlers.message_handler import handle_text_message

        await handle_text_message(
            parsed=parsed,
            ngo=ngo,
            staff=staff,
            ngo_settings=ngo_settings,
            db=db,
        )


async def _load_ngo_cached(
    ngo_slug: str,
    db: AsyncSession,
    bound_log: structlog.stdlib.BoundLogger,
) -> tuple[Optional[NGO], list[NGOSettings]]:
    """
    Load NGO + settings, trying Redis first to avoid a DB round-trip per update.

    NGO config (enabled agents, group ID) changes infrequently — a 5-minute
    cache dramatically reduces DB load under moderate Telegram traffic.
    We cache only a presence sentinel; the actual rows always come from DB so
    encrypted tokens are never written to Redis.
    """
    from app.core.redis_client import cache_get, cache_set

    cache_key = f"{_NGO_CACHE_PREFIX}{ngo_slug}"
    try:
        cached = await cache_get(cache_key)
        if cached:
            # cache_get already increments hit/miss metrics; just load from DB
            ngo, ngo_settings = await _load_ngo_from_db(ngo_slug, db)
            return ngo, ngo_settings
    except Exception as exc:
        # Cache failure must never block the primary path
        bound_log.warning("ngo_cache_read_failed", error=str(exc))

    ngo, ngo_settings = await _load_ngo_from_db(ngo_slug, db)

    if ngo is not None:
        try:
            payload = json.dumps({"ngo_id": str(ngo.id), "slug": ngo_slug})
            await cache_set(cache_key, payload, ttl_seconds=_NGO_CACHE_TTL_SECONDS)
        except Exception as exc:
            bound_log.warning("ngo_cache_write_failed", error=str(exc))

    return ngo, ngo_settings


async def _find_active_thread(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[ConversationThread]:
    """
    Return the most-recently-active open thread for this staff member, or None.

    Used to let follow-up messages (no @mention) continue an ongoing session
    without forcing the user to re-mention the bot every turn.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    result = await db.execute(
        select(ConversationThread)
        .where(
            ConversationThread.ngo_id == ngo_id,
            ConversationThread.staff_id == staff_id,
            ConversationThread.is_active.is_(True),
            ConversationThread.last_activity_at >= cutoff,
        )
        .order_by(ConversationThread.last_activity_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _load_ngo_from_db(
    ngo_slug: str,
    db: AsyncSession,
) -> tuple[Optional[NGO], list[NGOSettings]]:
    """Fetch NGO and its settings rows in a single query."""
    result = await db.execute(
        select(NGO).where(NGO.slug == ngo_slug)
    )
    ngo: Optional[NGO] = result.scalar_one_or_none()
    if ngo is None:
        return None, []

    settings_result = await db.execute(
        select(NGOSettings).where(NGOSettings.ngo_id == ngo.id)
    )
    ngo_settings: list[NGOSettings] = list(settings_result.scalars().all())
    return ngo, ngo_settings
