from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.ngo import NGO
    from app.models.reminder import Reminder, ReminderLog

logger = get_logger(__name__)


class CommsChannel(str, Enum):
    TELEGRAM = "telegram"
    SMS = "sms"
    EMAIL = "email"


async def send_reminder_to_target(
    channel: CommsChannel,
    message: str,
    reminder: "Reminder",
    ngo: "NGO",
    db: "AsyncSession",
) -> bool:
    """
    Routes a reminder to the correct channel based on reminder.target_details.

    target_details structure per channel:
      - telegram: {"chat_id": 12345} or {"audience": "all_staff"}
      - sms:      {"phones": ["+919876543210", ...]} or {"staff_ids": [...]}
      - email:    {"emails": [...]} or {"staff_ids": [...]}

    Returns True if all sends succeeded, False if any failed.
    """
    target = reminder.target_details or {}

    if channel == CommsChannel.TELEGRAM:
        return await _dispatch_telegram(message, target, ngo, db)

    if channel == CommsChannel.SMS:
        return await _dispatch_sms(message, target, ngo, db)

    if channel == CommsChannel.EMAIL:
        return await _dispatch_email(message, target, ngo, db)

    logger.error("unknown_channel", channel=channel, ngo_slug=ngo.slug)
    return False


async def _dispatch_telegram(
    message: str,
    target: dict,
    ngo: "NGO",
    db: "AsyncSession",
) -> bool:
    from app.comms.telegram_sender import send_to_group, send_to_staff

    # Explicit chat_id takes precedence over audience-based routing
    if "chat_id" in target:
        from app.bot.ngo_bot_registry import bot_registry
        msg = await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=target["chat_id"],
            text=message,
            parse_mode="HTML",
        )
        return msg is not None

    audience = target.get("audience", "group")

    if audience == "all_staff":
        from app.models.staff import Staff
        result = await db.execute(
            select(Staff).where(Staff.ngo_id == ngo.id, Staff.is_active.is_(True))
        )
        staff_list = result.scalars().all()
        # Any single failure makes the overall result False
        results = [await send_to_staff(ngo, s, message) for s in staff_list]
        return all(r is not None for r in results)

    # Default: send to the NGO group chat
    msg_id = await send_to_group(ngo, message)
    return msg_id is not None


async def _dispatch_sms(
    message: str,
    target: dict,
    ngo: "NGO",
    db: "AsyncSession",
) -> bool:
    from app.comms.sms import send_sms

    phones: list[str] = list(target.get("phones", []))

    # Resolve staff_ids to phone numbers when explicit phones aren't provided
    if not phones and "staff_ids" in target:
        phones = await _phones_for_staff_ids(target["staff_ids"], ngo, db)

    if not phones:
        logger.warning("sms_no_recipients", ngo_slug=ngo.slug)
        return False

    results = await _gather_bool(
        [send_sms(p, message, ngo.slug) for p in phones]
    )
    return all(results)


async def _dispatch_email(
    message: str,
    target: dict,
    ngo: "NGO",
    db: "AsyncSession",
) -> bool:
    from app.comms.email import send_email

    emails: list[tuple[str, str]] = [
        (addr, "") for addr in target.get("emails", [])
    ]

    # Resolve staff_ids to (email, name) pairs when explicit emails aren't provided
    if not emails and "staff_ids" in target:
        emails = await _emails_for_staff_ids(target["staff_ids"], ngo, db)

    if not emails:
        logger.warning("email_no_recipients", ngo_slug=ngo.slug)
        return False

    results = await _gather_bool(
        [send_email(addr, name, "Reminder", message, ngo) for addr, name in emails]
    )
    return all(results)


async def _phones_for_staff_ids(
    staff_ids: list[str],
    ngo: "NGO",
    db: "AsyncSession",
) -> list[str]:
    from app.models.staff import Staff

    parsed_ids = [uuid.UUID(sid) for sid in staff_ids if sid]
    if not parsed_ids:
        return []
    result = await db.execute(
        select(Staff.phone).where(
            Staff.id.in_(parsed_ids),
            Staff.ngo_id == ngo.id,
            Staff.phone.isnot(None),
        )
    )
    return [row[0] for row in result.all() if row[0]]


async def _emails_for_staff_ids(
    staff_ids: list[str],
    ngo: "NGO",
    db: "AsyncSession",
) -> list[tuple[str, str]]:
    from app.models.staff import Staff

    parsed_ids = [uuid.UUID(sid) for sid in staff_ids if sid]
    if not parsed_ids:
        return []
    result = await db.execute(
        select(Staff.email, Staff.name).where(
            Staff.id.in_(parsed_ids),
            Staff.ngo_id == ngo.id,
            Staff.email.isnot(None),
        )
    )
    return [(row[0], row[1]) for row in result.all() if row[0]]


async def _gather_bool(coros: list) -> list[bool]:
    import asyncio
    # Never raises — all channel functions already handle their own errors
    return list(await asyncio.gather(*coros))


async def send_notification(
    message: str,
    ngo: "NGO",
    channels: list[CommsChannel],
    recipients: list[dict],  # [{"name": "...", "phone": "...", "email": "...", "telegram_id": ...}]
    subject: Optional[str] = None,
    db: Optional["AsyncSession"] = None,
) -> dict:
    """
    Multi-channel send. Attempts each channel for each recipient.
    Returns per-channel result dict: {"telegram": {"sent": 3, "failed": 0}, ...}.
    Never raises — all errors are captured in the return dict.
    """
    import asyncio

    results: dict[str, dict] = {}

    for channel in channels:
        channel_results = {"sent": 0, "failed": 0}

        try:
            if channel == CommsChannel.TELEGRAM:
                channel_results = await _notify_telegram(recipients, ngo)

            elif channel == CommsChannel.SMS:
                channel_results = await _notify_sms(recipients, message, ngo)

            elif channel == CommsChannel.EMAIL:
                channel_results = await _notify_email(
                    recipients, message, subject or "Notification", ngo
                )

        except Exception as exc:
            # Belt-and-suspenders: individual senders don't raise, but protect here too
            logger.error(
                "notification_channel_error",
                ngo_slug=ngo.slug,
                channel=channel.value,
                error=str(exc),
            )
            channel_results = {"sent": 0, "failed": len(recipients), "error": str(exc)}

        results[channel.value] = channel_results

    return results


async def _notify_telegram(
    recipients: list[dict],
    ngo: "NGO",
) -> dict:
    from app.bot.ngo_bot_registry import bot_registry

    sent = 0
    failed = 0
    for r in recipients:
        tid = r.get("telegram_id")
        if not tid:
            failed += 1
            continue
        msg = await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=int(tid),
            text=r.get("message", ""),  # per-recipient message override or default
            parse_mode="HTML",
        )
        if msg is not None:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


async def _notify_sms(
    recipients: list[dict],
    message: str,
    ngo: "NGO",
) -> dict:
    from app.comms.sms import send_bulk_sms

    sms_recipients = [
        {"phone": r["phone"], "name": r.get("name", "")}
        for r in recipients
        if r.get("phone")
    ]
    failed_no_phone = len(recipients) - len(sms_recipients)
    result = await send_bulk_sms(sms_recipients, message, ngo.slug)
    return {
        "sent": result["sent"],
        "failed": result["failed"] + failed_no_phone,
        "errors": result.get("errors", []),
    }


async def _notify_email(
    recipients: list[dict],
    body: str,
    subject: str,
    ngo: "NGO",
) -> dict:
    from app.comms.email import send_bulk_email

    email_recipients = [
        {"email": r["email"], "name": r.get("name", ""), "context": {}}
        for r in recipients
        if r.get("email")
    ]
    failed_no_email = len(recipients) - len(email_recipients)
    result = await send_bulk_email(email_recipients, subject, body, ngo)
    return {
        "sent": result["sent"],
        "failed": result["failed"] + failed_no_email,
    }


# ---------------------------------------------------------------------------
# Legacy entrypoint — kept for callback_handler compatibility
# ---------------------------------------------------------------------------

async def dispatch_reminder(
    reminder_log: "ReminderLog",
    ngo: "NGO",
    db: "AsyncSession",
) -> None:
    """
    Dispatches an approved reminder via its configured channel.
    Raises on failure so the callback handler can surface it to the admin.
    """
    from app.models.reminder import Reminder

    channel_str = reminder_log.sent_via
    content = reminder_log.content

    bound_log = logger.bind(
        ngo_slug=ngo.slug,
        reminder_log_id=str(reminder_log.id),
        channel=channel_str,
    )

    try:
        channel = CommsChannel(channel_str)
    except ValueError:
        raise ValueError(f"Unknown delivery channel: {channel_str!r}")

    if channel == CommsChannel.TELEGRAM:
        from app.bot.ngo_bot_registry import bot_registry

        if ngo.telegram_group_chat_id is None:
            raise RuntimeError("NGO has no registered Telegram group — cannot send reminder")

        msg = await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=ngo.telegram_group_chat_id,
            text=content,
            parse_mode="HTML",
        )
        if msg is None:
            raise RuntimeError("Telegram send returned None — check bot_registry logs")

    elif channel == CommsChannel.SMS:
        # Load the parent Reminder to get target_details
        result = await db.execute(
            select(Reminder).where(Reminder.id == reminder_log.reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if reminder is None:
            raise RuntimeError(f"Reminder {reminder_log.reminder_id} not found")

        success = await _dispatch_sms(content, reminder.target_details or {}, ngo, db)
        if not success:
            raise RuntimeError("SMS dispatch failed — see sms logs for details")

    elif channel == CommsChannel.EMAIL:
        result = await db.execute(
            select(Reminder).where(Reminder.id == reminder_log.reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if reminder is None:
            raise RuntimeError(f"Reminder {reminder_log.reminder_id} not found")

        success = await _dispatch_email(content, reminder.target_details or {}, ngo, db)
        if not success:
            raise RuntimeError("Email dispatch failed — see email logs for details")

    reminder_log.status = "sent"
    await db.flush()
    bound_log.info("reminder_dispatched")
