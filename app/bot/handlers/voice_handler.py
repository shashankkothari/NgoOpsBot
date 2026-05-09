"""
Voice message handler — download, transcribe, then reuse the text pipeline.

Voice files are downloaded to memory (not disk) because Railway's filesystem
is ephemeral across restarts. Files under 25 MB (Telegram's voice cap) fit
comfortably in memory; beyond that Telegram simply won't deliver them.
"""

from __future__ import annotations

import io
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.message_handler import handle_text_message
from app.bot.ngo_bot_registry import bot_registry
from app.bot.update_parser import ParsedUpdate
from app.core.logging import get_logger
from app.core.metrics import messages_processed, whisper_transcriptions
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff

log: structlog.stdlib.BoundLogger = get_logger(__name__)

_TRANSCRIBING_MESSAGE = "🎙️ Transcribing your voice note..."
_TRANSCRIPTION_FAILED_MESSAGE = (
    "Sorry, I couldn't transcribe your voice note. Please try typing your question."
)


async def handle_voice_message(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Staff,
    ngo_settings: list[NGOSettings],
    db: AsyncSession,
) -> None:
    """
    Full voice pipeline: download → transcribe → delegate to text handler.
    """
    ngo_slug = ngo.slug
    voice_data: Optional[dict[str, Any]] = parsed.voice

    bound_log = log.bind(
        ngo_slug=ngo_slug,
        staff_id=str(staff.id),
        telegram_user_id=parsed.telegram_user_id,
        message_id=parsed.message_id,
    )

    if voice_data is None:
        # Should never happen given routing logic, but guard defensively
        bound_log.warning("voice_handler_called_without_voice_data")
        return

    file_id: str = voice_data.get("file_id", "")
    file_size: int = voice_data.get("file_size", 0)
    duration: int = voice_data.get("duration", 0)

    bound_log.info(
        "voice_message_received",
        file_size_bytes=file_size,
        duration_seconds=duration,
    )

    # --- Step 1: Download voice file to memory --------------------------------
    bot = bot_registry._bots.get(ngo_slug)
    if bot is None:
        bound_log.error("voice_download_no_bot")
        return

    try:
        tg_file = await bot.get_file(file_id)
        audio_buffer = io.BytesIO()
        await tg_file.download_to_memory(audio_buffer)
        audio_buffer.seek(0)
    except Exception as exc:
        bound_log.error(
            "voice_download_failed",
            error=str(exc),
            exc_info=True,
        )
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name="none", message_type="voice"
        ).inc()
        await bot_registry.send_message(ngo_slug, parsed.chat_id, _TRANSCRIPTION_FAILED_MESSAGE)
        return

    # --- Step 2: Notify staff transcription is in progress --------------------
    await bot_registry.send_message(ngo_slug, parsed.chat_id, _TRANSCRIBING_MESSAGE)

    # --- Step 3: Call Whisper -------------------------------------------------
    try:
        from app.integrations.whisper import transcribe_audio

        transcribed_text = await transcribe_audio(
            audio_data=audio_buffer,
            language=ngo.language or "en",
        )
    except Exception as exc:
        bound_log.error(
            "whisper_transcription_failed",
            error=str(exc),
            # Log duration not content — duration is diagnostic, content is PII
            duration_seconds=duration,
            exc_info=True,
        )
        whisper_transcriptions.labels(ngo_slug=ngo_slug, status="error").inc()
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name="none", message_type="voice"
        ).inc()
        await bot_registry.send_message(ngo_slug, parsed.chat_id, _TRANSCRIPTION_FAILED_MESSAGE)
        return

    # --- Step 4 & 5: Log outcome (no content!) and track metric ---------------
    bound_log.info(
        "whisper_transcription_complete",
        # Log char count as a proxy for success/length without exposing content
        transcribed_chars=len(transcribed_text),
        duration_seconds=duration,
    )
    whisper_transcriptions.labels(ngo_slug=ngo_slug, status="success").inc()

    if not transcribed_text.strip():
        bound_log.info("voice_transcription_empty")
        await bot_registry.send_message(
            ngo_slug,
            parsed.chat_id,
            "I couldn't make out anything from that voice note. Please try again.",
        )
        messages_processed.labels(
            ngo_slug=ngo_slug, agent_name="none", message_type="voice"
        ).inc()
        return

    # --- Step 6: Hand off to text handler as if the user had typed it ---------
    # Swap the parsed text with the transcription; everything else is identical
    text_parsed = ParsedUpdate(
        update_id=parsed.update_id,
        chat_id=parsed.chat_id,
        message_id=parsed.message_id,
        telegram_user_id=parsed.telegram_user_id,
        username=parsed.username,
        first_name=parsed.first_name,
        text=transcribed_text,
        voice=None,
        is_command=False,
        command=None,
        command_args=None,
        is_group_message=parsed.is_group_message,
        bot_mentioned=parsed.bot_mentioned,
        reply_to_bot=parsed.reply_to_bot,
        raw_update=parsed.raw_update,
    )

    await handle_text_message(
        parsed=text_parsed,
        ngo=ngo,
        staff=staff,
        ngo_settings=ngo_settings,
        db=db,
    )
    # handle_text_message tracks messages_processed for the voice message type "text"
    # so we also track one for voice to give an accurate split in dashboards
    messages_processed.labels(
        ngo_slug=ngo_slug, agent_name="voice", message_type="voice"
    ).inc()
