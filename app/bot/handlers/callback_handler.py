"""
Inline keyboard callback handler — primarily used for reminder approval flow.

Callbacks use a structured "action:id" format so a single handler can dispatch
to multiple flows without maintaining external state. The colon separator is safe
because Telegram callback_data is an opaque string up to 64 bytes.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ngo_bot_registry import bot_registry
from app.core.logging import get_logger
from app.core.metrics import reminders_sent
from app.models.ngo import NGO
from app.models.reminder import ReminderLog
from app.models.staff import Staff

log: structlog.stdlib.BoundLogger = get_logger(__name__)

_APPROVED_SUFFIX = "\n\n✅ <b>Approved</b>"
_REJECTED_SUFFIX = "\n\n❌ <b>Rejected</b>"


async def handle_callback_query(
    update_data: dict[str, Any],
    ngo: NGO,
    db: AsyncSession,
) -> None:
    """
    Dispatch inline keyboard callback queries.

    We answer every callback_query regardless of outcome to dismiss the Telegram
    loading spinner — an unanswered callback_query leaves a persistent spinner in
    the UI which looks broken to users.
    """
    callback_query = update_data.get("callback_query", {})
    callback_data: str = callback_query.get("data", "")
    callback_id: str = callback_query.get("id", "")
    from_user: dict[str, Any] = callback_query.get("from", {})
    message: dict[str, Any] = callback_query.get("message", {})

    telegram_user_id: int = from_user.get("id", 0)
    chat_id: int = message.get("chat", {}).get("id", 0)
    message_id: int = message.get("message_id", 0)
    original_text: str = message.get("text") or message.get("caption") or ""

    bound_log = log.bind(
        ngo_slug=ngo.slug,
        telegram_user_id=telegram_user_id,
        callback_data=callback_data,
        callback_id=callback_id,
    )

    # --- 1. Parse action and resource ID from callback data -------------------
    # Format: "reminder_approve:{uuid}" or "reminder_reject:{uuid}"
    parts = callback_data.split(":", 1)
    if len(parts) != 2:
        bound_log.warning("callback_malformed_data")
        await _answer_callback(ngo.slug, callback_id, "Invalid callback data.")
        return

    action, resource_id_str = parts[0], parts[1]

    if action not in ("reminder_approve", "reminder_reject"):
        # Unknown callback action — log and silently dismiss
        bound_log.info("callback_unknown_action", action=action)
        await _answer_callback(ngo.slug, callback_id, "")
        return

    # --- 2. Load ReminderLog from DB ------------------------------------------
    try:
        reminder_log_id = uuid.UUID(resource_id_str)
    except ValueError:
        bound_log.warning("callback_invalid_uuid", resource_id=resource_id_str)
        await _answer_callback(ngo.slug, callback_id, "Invalid reminder ID.")
        return

    result = await db.execute(
        select(ReminderLog).where(
            ReminderLog.id == reminder_log_id,
            ReminderLog.ngo_id == ngo.id,
        )
    )
    reminder_log = result.scalar_one_or_none()

    if reminder_log is None:
        bound_log.warning("callback_reminder_log_not_found", reminder_log_id=str(reminder_log_id))
        await _answer_callback(ngo.slug, callback_id, "Reminder not found.")
        return

    # Idempotency: already actioned reminders should not be processed twice
    if reminder_log.status in ("approved", "rejected", "sent"):
        bound_log.info(
            "callback_reminder_already_actioned",
            current_status=reminder_log.status,
        )
        await _answer_callback(
            ngo.slug, callback_id, f"Already {reminder_log.status}."
        )
        return

    # --- 3. Verify the staff member who clicked is an admin -------------------
    staff_result = await db.execute(
        select(Staff).where(
            Staff.ngo_id == ngo.id,
            Staff.telegram_user_id == telegram_user_id,
            Staff.is_active.is_(True),
        )
    )
    staff = staff_result.scalar_one_or_none()

    if staff is None or staff.role != "admin":
        bound_log.info(
            "callback_reminder_approval_denied",
            is_known_staff=staff is not None,
            role=staff.role if staff else None,
        )
        await _answer_callback(ngo.slug, callback_id, "Only admins can approve reminders.")
        return

    # --- 4. Update ReminderLog status -----------------------------------------
    is_approve = action == "reminder_approve"
    reminder_log.status = "approved" if is_approve else "rejected"
    reminder_log.approved_by_staff_id = staff.id
    await db.flush()

    bound_log.info(
        "reminder_actioned",
        reminder_log_id=str(reminder_log_id),
        status=reminder_log.status,
        admin_staff_id=str(staff.id),
    )

    # --- 5. Trigger delivery if approved --------------------------------------
    if is_approve:
        try:
            from app.comms.dispatcher import dispatch_reminder

            await dispatch_reminder(reminder_log=reminder_log, ngo=ngo, db=db)
            reminders_sent.labels(
                ngo_slug=ngo.slug, channel=reminder_log.sent_via
            ).inc()
        except Exception as exc:
            bound_log.error(
                "reminder_dispatch_failed",
                reminder_log_id=str(reminder_log_id),
                error=str(exc),
                exc_info=True,
            )
            await _answer_callback(ngo.slug, callback_id, "Approved, but send failed — check logs.")
            return

    # --- 6. Edit original message to reflect the decision (preserves audit trail) ----
    suffix = _APPROVED_SUFFIX if is_approve else _REJECTED_SUFFIX
    updated_text = original_text + suffix
    bot = bot_registry._bots.get(ngo.slug)
    if bot:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=updated_text,
                parse_mode="HTML",
                # Remove inline keyboard after action to prevent double-clicks
                reply_markup=None,
            )
        except Exception as exc:
            # Edit failure is cosmetic — the DB already reflects the decision
            bound_log.warning(
                "callback_edit_message_failed",
                error=str(exc),
            )

    action_word = "approved" if is_approve else "rejected"
    await _answer_callback(ngo.slug, callback_id, f"Reminder {action_word}.")


async def _answer_callback(ngo_slug: str, callback_query_id: str, text: str) -> None:
    """Answer the callback query to dismiss Telegram's loading spinner."""
    bot = bot_registry._bots.get(ngo_slug)
    if bot is None:
        return
    try:
        await bot.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text[:200] if text else None,  # Telegram caps popup text at 200 chars
        )
    except Exception as exc:
        log.debug(
            "answer_callback_failed",
            ngo_slug=ngo_slug,
            callback_query_id=callback_query_id,
            error=str(exc),
        )
