"""
Unit tests for app.bot.update_parser.parse_update()

Tests cover what parse_update() returns — not how it's implemented.
All cases use plain dicts matching the Telegram Bot API JSON schema.
"""

from __future__ import annotations

import pytest

from app.bot.update_parser import ParsedUpdate, parse_update

BOT_USERNAME = "testbot"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(
    *,
    update_id: int = 100,
    text: str | None = "hello",
    chat_type: str = "supergroup",
    chat_id: int = -1001234567890,
    user_id: int = 42,
    is_bot: bool = False,
    username: str | None = "priya",
    first_name: str = "Priya",
    entities: list | None = None,
    voice: dict | None = None,
    reply_to_message: dict | None = None,
    caption: str | None = None,
) -> dict:
    message: dict = {
        "message_id": 1,
        "from": {
            "id": user_id,
            "is_bot": is_bot,
            "first_name": first_name,
            "username": username,
        },
        "chat": {"id": chat_id, "type": chat_type},
        "date": 1700000000,
    }
    if text is not None:
        message["text"] = text
    if caption is not None:
        message["caption"] = caption
    if entities is not None:
        message["entities"] = entities
    if voice is not None:
        message["voice"] = voice
    if reply_to_message is not None:
        message["reply_to_message"] = reply_to_message

    return {"update_id": update_id, "message": message}


# ---------------------------------------------------------------------------
# Basic field mapping
# ---------------------------------------------------------------------------

def test_text_message_in_group_chat_returns_parsed_update():
    update = _make_update(text="hello world", chat_type="supergroup", chat_id=-999)
    result = parse_update(update, BOT_USERNAME)

    assert isinstance(result, ParsedUpdate)
    assert result.update_id == 100
    assert result.chat_id == -999
    assert result.text == "hello world"
    assert result.is_group_message is True
    assert result.is_command is False
    assert result.command is None
    assert result.voice is None
    assert result.bot_mentioned is False
    assert result.reply_to_bot is False
    assert result.telegram_user_id == 42
    assert result.username == "priya"
    assert result.first_name == "Priya"


def test_private_dm_sets_is_group_message_false():
    update = _make_update(text="private", chat_type="private", chat_id=12345)
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_group_message is False


def test_group_chat_type_group_sets_is_group_message_true():
    update = _make_update(text="hi", chat_type="group", chat_id=-5000)
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_group_message is True


# ---------------------------------------------------------------------------
# Voice messages
# ---------------------------------------------------------------------------

def test_voice_message_populates_voice_field_and_text_is_none():
    voice_obj = {"file_id": "abc123", "duration": 5, "mime_type": "audio/ogg"}
    update = _make_update(text=None, voice=voice_obj)
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.voice == voice_obj
    assert result.text is None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def test_command_help_sets_is_command_and_command_name():
    update = _make_update(
        text="/help",
        entities=[{"type": "bot_command", "offset": 0, "length": 5}],
    )
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_command is True
    assert result.command == "help"
    assert result.command_args is None


def test_command_with_bot_suffix_strips_botname():
    update = _make_update(
        text="/help@testbot",
        entities=[{"type": "bot_command", "offset": 0, "length": 13}],
    )
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_command is True
    assert result.command == "help"


def test_command_with_args_extracts_args():
    update = _make_update(
        text="/status check now",
        entities=[{"type": "bot_command", "offset": 0, "length": 7}],
    )
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_command is True
    assert result.command == "status"
    assert result.command_args == "check now"


def test_non_zero_offset_entity_not_treated_as_command():
    # entity at offset 5 is not a leading command
    update = _make_update(
        text="hello /help",
        entities=[{"type": "bot_command", "offset": 6, "length": 5}],
    )
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.is_command is False
    assert result.command is None


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------

def test_bot_mentioned_in_text_sets_flag():
    update = _make_update(text="@testbot what's the status?")
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.bot_mentioned is True


def test_bot_not_mentioned_when_different_username():
    update = _make_update(text="@otherbot help me")
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.bot_mentioned is False


def test_bot_mention_is_case_insensitive():
    update = _make_update(text="Hey @TESTBOT can you help?")
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.bot_mentioned is True


# ---------------------------------------------------------------------------
# Reply-to-bot
# ---------------------------------------------------------------------------

def test_reply_to_bot_message_sets_flag():
    reply_msg = {
        "message_id": 10,
        "from": {"id": 999, "is_bot": True, "first_name": "MyBot"},
        "chat": {"id": -1001234567890, "type": "supergroup"},
        "text": "I am a bot reply",
        "date": 1699999999,
    }
    update = _make_update(text="thanks!", reply_to_message=reply_msg)
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.reply_to_bot is True


def test_reply_to_human_message_does_not_set_flag():
    reply_msg = {
        "message_id": 11,
        "from": {"id": 555, "is_bot": False, "first_name": "Ravi"},
        "chat": {"id": -1001234567890, "type": "supergroup"},
        "text": "human message",
        "date": 1699999998,
    }
    update = _make_update(text="replied!", reply_to_message=reply_msg)
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.reply_to_bot is False


# ---------------------------------------------------------------------------
# Filtered (ignored) update types → None
# ---------------------------------------------------------------------------

def test_message_from_bot_returns_none():
    update = _make_update(text="I am a bot", is_bot=True)
    assert parse_update(update, BOT_USERNAME) is None


def test_edited_message_returns_none():
    update = {
        "update_id": 200,
        "edited_message": {
            "message_id": 5,
            "from": {"id": 99, "is_bot": False, "first_name": "X"},
            "chat": {"id": -100, "type": "supergroup"},
            "text": "edited text",
            "date": 1700000001,
            "edit_date": 1700000099,
        },
    }
    assert parse_update(update, BOT_USERNAME) is None


def test_channel_post_returns_none():
    update = {
        "update_id": 300,
        "channel_post": {
            "message_id": 7,
            "chat": {"id": -100, "type": "channel"},
            "text": "channel message",
            "date": 1700000002,
        },
    }
    assert parse_update(update, BOT_USERNAME) is None


def test_empty_update_dict_returns_none_without_exception():
    result = parse_update({}, BOT_USERNAME)
    assert result is None


def test_update_with_no_from_field_returns_none():
    # Channel posts forwarded into groups have no 'from'
    update = {
        "update_id": 400,
        "message": {
            "message_id": 8,
            # no 'from' key
            "chat": {"id": -100, "type": "supergroup"},
            "text": "forwarded channel content",
            "date": 1700000003,
        },
    }
    assert parse_update(update, BOT_USERNAME) is None


# ---------------------------------------------------------------------------
# Raw update preservation
# ---------------------------------------------------------------------------

def test_raw_update_is_preserved_on_result():
    update = _make_update(text="keep me")
    result = parse_update(update, BOT_USERNAME)

    assert result is not None
    assert result.raw_update is update
