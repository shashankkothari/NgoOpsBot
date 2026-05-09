from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.ngo import NGO
    from app.models.staff import Staff

logger = get_logger(__name__)

# Telegram's hard cap per message — exceeding it silently truncates or errors
_TELEGRAM_MAX_CHARS = 4096


async def send_to_group(
    ngo: "NGO",
    message: str,
    reply_markup=None,
    parse_mode: str = "HTML",  # HTML is safer than Markdown for dynamic content
) -> Optional[int]:
    """
    Sends a message to the NGO's Telegram group chat.
    Returns message_id of the last chunk on success, None on failure.
    """
    from app.bot.ngo_bot_registry import bot_registry

    if ngo.telegram_group_chat_id is None:
        logger.warning("send_to_group_no_chat_id", ngo_slug=ngo.slug)
        return None

    # Chunk long messages — Telegram rejects anything over 4096 chars
    chunks = [
        message[i : i + _TELEGRAM_MAX_CHARS]
        for i in range(0, max(len(message), 1), _TELEGRAM_MAX_CHARS)
    ]

    last_message_id: Optional[int] = None
    for idx, chunk in enumerate(chunks):
        # Only attach reply_markup to the last chunk so buttons appear once
        markup = reply_markup if idx == len(chunks) - 1 else None
        msg = await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=ngo.telegram_group_chat_id,
            text=chunk,
            parse_mode=parse_mode,
            reply_markup=markup,
        )
        if msg is None:
            logger.error(
                "send_to_group_failed",
                ngo_slug=ngo.slug,
                chat_id=ngo.telegram_group_chat_id,
                chunk_index=idx,
            )
            return None
        last_message_id = msg.message_id

    return last_message_id


async def send_to_staff(
    ngo: "NGO",
    staff: "Staff",
    message: str,
) -> Optional[int]:
    """
    Sends a direct message to a specific staff member.
    Only works if the staff member has previously started a DM with the bot.
    """
    from app.bot.ngo_bot_registry import bot_registry

    # Telegram DMs require the user to have initiated contact with the bot first
    if not staff.telegram_user_id:
        logger.warning(
            "send_to_staff_no_chat_id",
            ngo_slug=ngo.slug,
            staff_id=str(staff.id),
            staff_name=staff.name,
        )
        return None

    chunks = [
        message[i : i + _TELEGRAM_MAX_CHARS]
        for i in range(0, max(len(message), 1), _TELEGRAM_MAX_CHARS)
    ]

    last_message_id: Optional[int] = None
    for idx, chunk in enumerate(chunks):
        msg = await bot_registry.send_message(
            ngo_slug=ngo.slug,
            chat_id=staff.telegram_user_id,
            text=chunk,
            parse_mode="HTML",
        )
        if msg is None:
            logger.error(
                "send_to_staff_failed",
                ngo_slug=ngo.slug,
                staff_id=str(staff.id),
                chunk_index=idx,
            )
            return None
        last_message_id = msg.message_id

    return last_message_id


async def notify_admin(
    ngo: "NGO",
    message: str,
    db: "AsyncSession",
) -> None:
    """
    Sends an alert to all admin staff members.
    Used for system alerts: Google auth expired, reminder send failed, etc.
    """
    from app.models.staff import Staff

    # Load admins fresh from DB — cached in-memory state could be stale
    result = await db.execute(
        select(Staff).where(
            Staff.ngo_id == ngo.id,
            Staff.role == "admin",
            Staff.is_active.is_(True),
        )
    )
    admins = result.scalars().all()

    if not admins:
        logger.warning("notify_admin_no_admins", ngo_slug=ngo.slug)
        return

    for admin in admins:
        msg_id = await send_to_staff(ngo, admin, message)
        if msg_id is None:
            logger.warning(
                "notify_admin_send_failed",
                ngo_slug=ngo.slug,
                staff_id=str(admin.id),
                staff_name=admin.name,
            )
        else:
            logger.info(
                "notify_admin_sent",
                ngo_slug=ngo.slug,
                staff_id=str(admin.id),
            )
