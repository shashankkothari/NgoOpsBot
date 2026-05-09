"""
Claude-powered message composer for background automation.

This is NOT a conversational agent — it has no conversation history and does
not subclass BaseAgent.  It is called by the scheduler and reminder engine to
produce ready-to-send text (reminders, donor emails, volunteer messages).

All calls use the platform Anthropic key, not the NGO's key, because these
are background platform operations that run outside any user session.  Cost
is therefore charged to the platform, not the NGO.

The three public coroutines share a single internal helper (_call_claude_for_comms)
so retry logic, metric recording, and fallback handling live in one place.
"""

from __future__ import annotations

import json
import time

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import external_api_latency
from app.models.ngo import NGO
from app.models.reminder import Reminder

logger = get_logger(__name__)
settings = get_settings()

# Shorter than the agent max — reminders must fit in a Telegram message comfortably.
_REMINDER_MAX_TOKENS = 500
_EMAIL_MAX_TOKENS = 800
_VOLUNTEER_MAX_TOKENS = 600

# Returned verbatim when the Claude call fails so the caller always gets a string.
_FALLBACK_REMINDER = (
    "Reminder: You have a pending action item. Please check your task list."
)
_FALLBACK_EMAIL = (
    "Dear {recipient},\n\nWe wanted to reach out regarding an important matter. "
    "Please get in touch with us at your earliest convenience.\n\nWarm regards,\n{ngo_name}"
)
_FALLBACK_VOLUNTEER = (
    "Hi {recipient},\n\nThank you for your time and contribution. "
    "We appreciate your support.\n\n{ngo_name} Team"
)

COMMS_SYSTEM_PROMPT = """
You are a communications assistant for an NGO. Your job is to write clear, warm, and action-oriented messages.

Rules:
- Be concise — the recipient is busy
- Be specific — include dates, amounts, names when provided
- Match the tone to the audience: formal for donors/board, friendly for volunteers/staff
- Write in the language specified
- For reminders: state what's needed, by when, and why it matters
- No corporate jargon, no filler phrases
"""


async def draft_reminder_message(
    reminder: Reminder,
    ngo: NGO,
    context: dict,
    language: str = "en",
) -> str:
    """
    Compose a natural-language reminder triggered by the scheduler.

    Claude generates fresh text each time — no static template — so the
    message reads as a genuine, context-aware notification rather than a
    bot-generated form letter.
    """
    # Serialise context to JSON so Claude receives structured data without
    # us needing to enumerate every possible field name upfront.
    context_json = json.dumps(context, ensure_ascii=False, default=str)

    user_prompt = (
        f"Write a reminder message for the following situation.\n\n"
        f"NGO: {ngo.name}\n"
        f"Reminder title: {reminder.title}\n"
        f"Reminder type: {reminder.reminder_type}\n"
        f"Additional context (JSON): {context_json}\n"
        f"Language: {language}\n\n"
        f"The message will be sent via Telegram to NGO staff. "
        f"Keep it under 200 words. State clearly what is needed and by when."
    )

    return await _call_claude_for_comms(
        user_prompt=user_prompt,
        language=language,
        max_tokens=_REMINDER_MAX_TOKENS,
        fallback=_FALLBACK_REMINDER,
    )


async def draft_donor_email(
    purpose: str,
    recipient_name: str,
    ngo: NGO,
    context: dict,
    language: str = "en",
) -> str:
    """
    Compose outbound donor email body text suitable for SendGrid.

    Returns plain text only — subject line and HTML wrapping are handled
    by the comms dispatcher so Claude doesn't need to produce them.
    """
    context_json = json.dumps(context, ensure_ascii=False, default=str)

    user_prompt = (
        f"Write the body of a donor email.\n\n"
        f"NGO: {ngo.name}\n"
        f"Purpose: {purpose}\n"
        f"Recipient name: {recipient_name}\n"
        f"Context (JSON): {context_json}\n"
        f"Language: {language}\n\n"
        f"Tone: warm and professional. Open with the recipient's name. "
        f"Be specific about amounts, dates, and impact where the context provides them. "
        f"End with a clear call-to-action. Plain text only — no HTML tags. "
        f"Keep under 300 words."
    )

    # Personalise fallback with actual values so it's not completely generic.
    fallback = _FALLBACK_EMAIL.format(
        recipient=recipient_name, ngo_name=ngo.name
    )

    return await _call_claude_for_comms(
        user_prompt=user_prompt,
        language=language,
        max_tokens=_EMAIL_MAX_TOKENS,
        fallback=fallback,
    )


async def draft_volunteer_message(
    purpose: str,
    recipient_name: str,
    ngo: NGO,
    context: dict,
    language: str = "en",
) -> str:
    """
    Compose a volunteer communication: onboarding welcome, event reminder, or thank-you.

    Volunteer messages use a friendlier, less formal register than donor emails
    — Claude is instructed accordingly via the user prompt rather than a
    separate system prompt to keep the helper count low.
    """
    context_json = json.dumps(context, ensure_ascii=False, default=str)

    user_prompt = (
        f"Write a message to a volunteer.\n\n"
        f"NGO: {ngo.name}\n"
        f"Purpose: {purpose}\n"
        f"Recipient name: {recipient_name}\n"
        f"Context (JSON): {context_json}\n"
        f"Language: {language}\n\n"
        f"Tone: warm, friendly, and encouraging — this is a volunteer, not a donor. "
        f"Be specific about event details, dates, or tasks from the context. "
        f"Plain text only. Keep under 200 words."
    )

    fallback = _FALLBACK_VOLUNTEER.format(
        recipient=recipient_name, ngo_name=ngo.name
    )

    return await _call_claude_for_comms(
        user_prompt=user_prompt,
        language=language,
        max_tokens=_VOLUNTEER_MAX_TOKENS,
        fallback=fallback,
    )


async def _call_claude_for_comms(
    user_prompt: str,
    language: str,
    max_tokens: int = _REMINDER_MAX_TOKENS,
    fallback: str = _FALLBACK_REMINDER,
) -> str:
    """
    Shared Claude call for all background message composition.

    Intentional design choices:
    - No conversation history: each call is stateless and produces one message.
    - Platform API key: background jobs are not NGO-initiated sessions.
    - No prompt caching: comms prompts are unique per call so caching would
      never hit; omitting cache_control avoids the overhead of the cache write.
    - Synchronous fallback: on any failure the caller receives a usable string
      so the scheduler/reminder engine never crashes the delivery pipeline.
    """
    # Language hint in the system prompt so Claude doesn't need to infer it.
    system_with_lang = (
        f"{COMMS_SYSTEM_PROMPT.strip()}\n\n"
        f"Respond in language code: {language}"
    )

    t0 = time.monotonic()
    try:
        # Platform key — cost is not attributed to any individual NGO.
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_with_lang,
            messages=[{"role": "user", "content": user_prompt}],
        )

        latency = time.monotonic() - t0

        # Record latency regardless of whether we read from cache (we don't).
        external_api_latency.labels(service="anthropic").observe(latency)

        usage = response.usage
        logger.info(
            "comms_claude_call",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=round(latency * 1000),
            # Never log prompt or response text — may contain PII.
        )

        # Extract first text block; guard against unexpected content shapes.
        for block in response.content:
            if block.type == "text":
                return block.text

        # Response contained no text block — return fallback rather than empty string.
        logger.warning("comms_claude_empty_response")
        return fallback

    except anthropic.APIError as exc:
        # APIError covers rate limits, auth errors, and 5xx responses.
        latency = time.monotonic() - t0
        external_api_latency.labels(service="anthropic").observe(latency)
        logger.error(
            "comms_claude_api_error",
            error=str(exc),
            latency_ms=round(latency * 1000),
        )
        return fallback

    except Exception as exc:
        # Broad catch so scheduler jobs never propagate an unhandled exception
        # from a message composition step into the delivery pipeline.
        latency = time.monotonic() - t0
        external_api_latency.labels(service="anthropic").observe(latency)
        logger.exception("comms_claude_unexpected_error", error=str(exc))
        return fallback
