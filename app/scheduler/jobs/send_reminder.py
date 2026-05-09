"""Telegram delivery helpers for the scheduler layer.

Three functions cover the three delivery paths:
  1. send_to_staff_group      — direct send, no approval required
  2. send_approval_request    — inline keyboard for admin approve/reject
  3. send_approved_external   — called by callback_handler after admin taps ✅
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.ngo_bot_registry import bot_registry
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.ngo import NGO
    from app.models.reminder import Reminder

logger = get_logger(__name__)


async def send_to_staff_group(
    ngo: "NGO",
    reminder: "Reminder",
    message_text: str,
) -> bool:
    """Send a formatted reminder to the NGO's Telegram staff group."""
    if ngo.telegram_group_chat_id is None:
        logger.error(
            "send_to_staff_group_no_chat_id",
            ngo_slug=ngo.slug,
            reminder_id=str(reminder.id),
        )
        return False

    # Bold title stands out in Telegram so staff notice it's a system reminder.
    formatted = f"*{reminder.title}*\n\n{message_text}"

    msg = await bot_registry.send_message(
        ngo_slug=ngo.slug,
        chat_id=ngo.telegram_group_chat_id,
        text=formatted,
        parse_mode="Markdown",
    )
    if msg is None:
        logger.error(
            "send_to_staff_group_failed",
            ngo_slug=ngo.slug,
            reminder_id=str(reminder.id),
        )
        return False

    logger.info(
        "send_to_staff_group_ok",
        ngo_slug=ngo.slug,
        reminder_id=str(reminder.id),
        message_id=msg.message_id,
    )
    return True


async def send_approval_request(
    ngo: "NGO",
    reminder: "Reminder",
    reminder_log_id: str,
    message_text: str,
) -> bool:
    """Send the draft message to the group with approve/reject inline buttons."""
    if ngo.telegram_group_chat_id is None:
        logger.error(
            "send_approval_request_no_chat_id",
            ngo_slug=ngo.slug,
            reminder_id=str(reminder.id),
        )
        return False

    # Embed the log ID in callback_data so the handler can load the exact log row.
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Send to recipients",
                callback_data=f"reminder_approve:{reminder_log_id}",
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"reminder_reject:{reminder_log_id}",
            ),
        ]
    ])

    preview = (
        f"*Reminder approval needed: {reminder.title}*\n\n"
        f"{message_text}\n\n"
        f"_An admin must approve before this message is sent to external recipients._"
    )

    msg = await bot_registry.send_message(
        ngo_slug=ngo.slug,
        chat_id=ngo.telegram_group_chat_id,
        text=preview,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    if msg is None:
        logger.error(
            "send_approval_request_failed",
            ngo_slug=ngo.slug,
            reminder_id=str(reminder.id),
            reminder_log_id=reminder_log_id,
        )
        return False

    logger.info(
        "send_approval_request_ok",
        ngo_slug=ngo.slug,
        reminder_id=str(reminder.id),
        reminder_log_id=reminder_log_id,
    )
    return True


async def send_approved_external(
    reminder_log_id: str,
    db: "AsyncSession",
) -> None:
    """Dispatch an approved reminder to external recipients and update the log."""
    import uuid

    from sqlalchemy import select

    from app.comms.dispatcher import CommsChannel, send_reminder_to_target
    from app.core.metrics import reminders_sent
    from app.models.ngo import NGO
    from app.models.reminder import Reminder, ReminderLog

    # Load the log and its parent reminder in one pass.
    log_result = await db.execute(
        select(ReminderLog).where(ReminderLog.id == uuid.UUID(reminder_log_id))
    )
    reminder_log = log_result.scalar_one_or_none()

    if reminder_log is None:
        logger.error("send_approved_external_log_not_found", reminder_log_id=reminder_log_id)
        return

    reminder_result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_log.reminder_id)
    )
    reminder = reminder_result.scalar_one_or_none()

    ngo_result = await db.execute(select(NGO).where(NGO.id == reminder_log.ngo_id))
    ngo = ngo_result.scalar_one_or_none()

    if reminder is None or ngo is None:
        logger.error(
            "send_approved_external_missing_data",
            reminder_log_id=reminder_log_id,
        )
        return

    channel_str = reminder_log.sent_via
    try:
        channel_enum = CommsChannel(channel_str)
    except ValueError:
        logger.error(
            "send_approved_external_bad_channel",
            channel=channel_str,
            reminder_log_id=reminder_log_id,
        )
        reminder_log.status = "failed"
        reminder_log.error_message = f"Unknown channel: {channel_str}"
        await db.commit()
        return

    success = await send_reminder_to_target(
        channel_enum, reminder_log.content, reminder, ngo, db
    )

    if success:
        reminder_log.status = "sent"
        reminders_sent.labels(ngo_slug=ngo.slug, channel=channel_str).inc()
        confirmation = (
            f"✅ Reminder *{reminder.title}* has been sent to recipients via {channel_str}."
        )
    else:
        reminder_log.status = "failed"
        reminder_log.error_message = f"Comms dispatcher failed for channel={channel_str}"
        confirmation = (
            f"❌ Failed to send reminder *{reminder.title}* via {channel_str}. "
            f"Check the application logs."
        )

    await db.commit()

    # Notify the group so admins know the outcome of the send.
    if ngo.telegram_group_chat_id:
        await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=ngo.telegram_group_chat_id,
            text=confirmation,
            parse_mode="Markdown",
        )

    logger.info(
        "send_approved_external_done",
        reminder_log_id=reminder_log_id,
        status=reminder_log.status,
        ngo_slug=ngo.slug,
    )
