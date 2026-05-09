"""
OpenAI Whisper integration for voice-to-text transcription.

We use the openai SDK's async client rather than httpx directly because the SDK
handles multipart encoding, retries, and error classification for us. The audio
file is passed as an in-memory BytesIO to avoid any disk I/O.
"""

from __future__ import annotations

import io

import structlog
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Module-level client — reused across calls to share the underlying httpx connection pool
_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client  # noqa: PLW0603
    if _openai_client is None:
        settings = get_settings()
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


async def transcribe_audio(
    audio_data: io.BytesIO,
    language: str = "en",
) -> str:
    """
    Transcribe audio bytes to text via Whisper API.

    `language` is a BCP-47 code (e.g. "en", "hi"). Passing it explicitly
    avoids Whisper's language auto-detection round-trip, cutting latency ~20%.

    Raises:
        openai.APIError: on network or API-level failure (caller handles this)
    """
    settings = get_settings()
    client = _get_client()

    # Whisper requires a filename with a recognised extension to infer codec
    audio_data.name = "voice.ogg"  # type: ignore[attr-defined]

    response = await client.audio.transcriptions.create(
        model=settings.WHISPER_MODEL,
        file=audio_data,
        language=language,
        response_format="text",
    )

    # openai SDK returns a str when response_format="text"
    return str(response).strip()
