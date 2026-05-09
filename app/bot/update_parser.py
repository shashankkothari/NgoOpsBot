"""
Parse raw Telegram JSON update dicts into a typed ParsedUpdate dataclass.

We parse manually from the dict rather than constructing a full
python-telegram-bot Update object because we never registered handlers —
we use the Bot API directly and process updates synchronously in our own
router. Constructing a PTB Update would require a bound Application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from app.core.logging import get_logger

log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass
class ParsedUpdate:
    update_id: int
    chat_id: int
    message_id: int
    telegram_user_id: int
    username: Optional[str]
    first_name: Optional[str]
    text: Optional[str]
    # Raw voice dict rather than PTB Voice object to avoid Application dependency
    voice: Optional[dict[str, Any]]
    is_command: bool
    # Command without the leading slash, e.g. "help", "status"
    command: Optional[str]
    command_args: Optional[str]
    is_group_message: bool
    bot_mentioned: bool
    # True when the user replies to a message sent by any bot
    reply_to_bot: bool
    raw_update: dict[str, Any]


def parse_update(update_data: dict[str, Any], bot_username: str) -> Optional[ParsedUpdate]:
    """
    Return a ParsedUpdate for supported update types, or None to silently ignore.

    We only handle 'message' updates. Edited messages, channel posts, inline
    queries etc. are intentionally ignored — they represent a different UX
    contract we have not designed for yet.
    """
    message = update_data.get("message")
    if not message:
        # Edited messages would match 'edited_message' — ignore intentionally
        log.debug(
            "update_ignored_no_message",
            update_id=update_data.get("update_id"),
            keys=list(update_data.keys()),
        )
        return None

    from_user = message.get("from")
    if not from_user:
        # Channel posts forwarded into groups have no 'from' field
        log.debug("update_ignored_no_from", update_id=update_data.get("update_id"))
        return None

    # Bots messaging other bots creates feedback loops we must not enter
    if from_user.get("is_bot", False):
        log.debug(
            "update_ignored_bot_sender",
            sender_id=from_user.get("id"),
            update_id=update_data.get("update_id"),
        )
        return None

    chat = message.get("chat", {})
    chat_type = chat.get("type", "")
    # "group" and "supergroup" are both valid group types in Telegram's model
    is_group_message = chat_type in ("group", "supergroup")

    raw_text: str = message.get("text") or message.get("caption") or ""
    voice: Optional[dict[str, Any]] = message.get("voice")

    # Extract command: Telegram marks entity type "bot_command" at offset 0
    is_command = False
    command: Optional[str] = None
    command_args: Optional[str] = None

    entities = message.get("entities") or []
    for entity in entities:
        if entity.get("type") == "bot_command" and entity.get("offset") == 0:
            is_command = True
            # Slice the command text from the entity length; strip leading slash
            length = entity.get("length", 0)
            raw_cmd = raw_text[:length].lstrip("/")
            # Commands in groups arrive as "/cmd@botname" — strip the @botname suffix
            if "@" in raw_cmd:
                raw_cmd = raw_cmd.split("@", 1)[0]
            command = raw_cmd.lower()
            remainder = raw_text[length:].strip()
            command_args = remainder if remainder else None
            break

    # @mention detection: case-insensitive substring search in the raw text
    bot_mentioned = False
    mention_target = f"@{bot_username}".lower()
    if raw_text and mention_target in raw_text.lower():
        bot_mentioned = True

    # Reply-to-bot: check if the message is a reply to a message sent by any bot
    reply_to_bot = False
    reply_to = message.get("reply_to_message")
    if reply_to:
        reply_from = reply_to.get("from", {})
        reply_to_bot = bool(reply_from.get("is_bot", False))

    update_id = update_data.get("update_id", 0)
    return ParsedUpdate(
        update_id=update_id,
        chat_id=chat.get("id", 0),
        message_id=message.get("message_id", 0),
        telegram_user_id=from_user.get("id", 0),
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
        text=raw_text if raw_text else None,
        voice=voice,
        is_command=is_command,
        command=command,
        command_args=command_args,
        is_group_message=is_group_message,
        bot_mentioned=bot_mentioned,
        reply_to_bot=reply_to_bot,
        raw_update=update_data,
    )
