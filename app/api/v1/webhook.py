"""
Telegram webhook endpoint — one URL per NGO, secret-authenticated.

URL pattern: POST /api/v1/webhook/{ngo_slug}/{secret}

Why the secret is in the URL path (not a header):
    Telegram's Bot API setWebhook accepts a `secret_token` parameter which
    causes Telegram to add an X-Telegram-Bot-Api-Secret-Token header.  We
    use a path-based secret instead because:
      1. The per-NGO webhook URL already embeds the NGO slug for routing —
         adding the secret in the same path avoids a second lookup.
      2. It works identically across all Telegram Bot API versions without
         requiring clients to support the optional secret_token parameter.
      3. Railway and Render log request paths but not headers — having the
         secret in the path would be a risk, but we never log the full path
         (we log only the slug, not the secret segment).

Rate limiting:
    Per-NGO sliding-window rate limiter (30 req/min) is enforced via Redis
    sorted sets.  This prevents replay storms and abuse even if an attacker
    obtains a valid webhook URL.
"""

from __future__ import annotations

import hmac
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ngo_router import route_update
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.rate_limiter import is_webhook_allowed
from app.models.ngo import NGO

log: structlog.stdlib.BoundLogger = get_logger(__name__)
# Prefix matches the convention used by admin routers in this package
router = APIRouter(prefix="/api/v1", tags=["webhook"])


@router.post("/webhook/{ngo_slug}/{secret}", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    ngo_slug: str,
    secret: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Receive a Telegram update, validate the secret, and dispatch in the background.

    We always return 200 — Telegram's retry policy will flood us with duplicate
    updates if we return anything else for transient errors. All errors are
    logged server-side. BackgroundTasks dispatch means this endpoint returns
    before Claude responds; Claude calls can take 20-30 s which would exceed
    Telegram's 60 s webhook timeout and trigger retry storms.
    """
    bound_log = log.bind(ngo_slug=ngo_slug)

    # --- Per-NGO rate limit (30 req/min sliding window) ----------------------
    allowed, remaining = await is_webhook_allowed(ngo_slug)
    if not allowed:
        bound_log.warning("webhook_rate_limited", remaining=remaining)
        # 429 signals to Telegram to back off; we do NOT return 200 here
        # because that would acknowledge receipt and suppress retries
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    # --- Parse raw body as JSON ----------------------------------------------
    try:
        update_data: dict[str, Any] = await request.json()
    except Exception as exc:
        bound_log.warning("webhook_invalid_json", error=str(exc))
        # 200 here: malformed body from Telegram is their bug; retrying won't fix it
        return {"ok": "true"}

    update_id = update_data.get("update_id", "unknown")
    bound_log = bound_log.bind(update_id=update_id)

    # --- Load NGO and validate secret (constant-time compare) ----------------
    result = await db.execute(
        select(NGO).where(NGO.slug == ngo_slug)
    )
    ngo: NGO | None = result.scalar_one_or_none()

    if ngo is None:
        bound_log.warning("webhook_ngo_not_found")
        # 200 so Telegram stops retrying; the NGO slug isn't going to appear later
        return {"ok": "true"}

    # hmac.compare_digest prevents timing-based secret enumeration.
    # Both sides are guaranteed str; encode() to bytes required by compare_digest.
    if not hmac.compare_digest(secret.encode(), ngo.webhook_secret.encode()):
        bound_log.warning("webhook_invalid_secret")
        # 403 signals a permanent auth failure — Telegram will not retry 4xx.
        # Empty detail body: no information leakage about why it failed.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if not ngo.is_active:
        bound_log.info("webhook_ngo_inactive")
        return {"ok": "true"}

    bound_log.info("webhook_update_received", update_type=_classify_update(update_data))

    # --- Dispatch to background, return 200 immediately ---------------------
    # A fresh DB session is created inside the task because the request-scoped
    # session closes when this handler returns.
    background_tasks.add_task(_process_update_background, ngo_slug, update_data)

    return {"ok": "true"}


async def _process_update_background(
    ngo_slug: str,
    update_data: dict[str, Any],
) -> None:
    """
    Process one Telegram update in a BackgroundTask with its own DB session.

    Background task exceptions are silent by default in Starlette — we
    must catch and log them ourselves or they disappear without a trace.
    """
    from app.core.database import AsyncSessionLocal

    bound_log = log.bind(ngo_slug=ngo_slug, update_id=update_data.get("update_id"))

    try:
        async with AsyncSessionLocal() as session:
            try:
                await route_update(ngo_slug, update_data, session)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                bound_log.error(
                    "background_update_processing_failed",
                    error=str(exc),
                    exc_info=True,
                )
    except Exception as exc:
        # Session creation failure — DB pool exhausted or misconfigured
        bound_log.error(
            "background_session_creation_failed",
            error=str(exc),
            exc_info=True,
        )


def _classify_update(update_data: dict[str, Any]) -> str:
    """Return a label for the update type — used only in log lines."""
    if "message" in update_data:
        msg = update_data["message"]
        if "voice" in msg:
            return "voice"
        entities = msg.get("entities") or []
        if any(e.get("type") == "bot_command" for e in entities):
            return "command"
        return "message"
    if "callback_query" in update_data:
        return "callback_query"
    if "edited_message" in update_data:
        return "edited_message"
    return "other"
