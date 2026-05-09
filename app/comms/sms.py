from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import external_api_latency, reminders_sent

logger = get_logger(__name__)
settings = get_settings()

# MSG91 Flow API supports templates + OTP and has better delivery than plain SMS
MSG91_FLOW_URL = "https://api.msg91.com/api/v5/flow/"
MSG91_SMS_URL = "https://api.msg91.com/api/v5/sms"

# Module-level client avoids TCP handshake overhead on every SMS send
_http_client: httpx.AsyncClient | None = None

# Max concurrent MSG91 requests — free tier throttles hard above this
_BULK_SEMAPHORE = asyncio.Semaphore(10)


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # Keepalive limit matches MSG91's server-side connection timeout
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


def normalize_phone(phone: str) -> str:
    # NGOs enter numbers in many formats (WhatsApp saved, with dashes, etc.)
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        # Bare 10-digit Indian mobile — prepend country code
        return "91" + digits
    if digits.startswith("0") and len(digits) == 11:
        # Old-style 0-prefixed STD format
        return "91" + digits[1:]
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if digits.startswith("+91"):
        return digits[1:]
    # Return as-is for non-Indian or already-normalised numbers
    return digits


async def send_sms(
    to_phone: str,
    message: str,
    ngo_slug: str,
    sender_id: Optional[str] = None,
) -> bool:
    """
    Sends a plain transactional SMS via MSG91.
    Returns True on success, False on failure (never raises — caller logs).
    """
    normalized = normalize_phone(to_phone)
    effective_sender = sender_id or settings.MSG91_SENDER_ID

    payload = {
        "sender": effective_sender,
        "route": "4",  # route 4 = transactional (DND-exempt) in MSG91
        "country": "91",
        "sms": [
            {
                "message": message[:918],  # 153 chars/part * 6 parts max
                "to": [normalized],
            }
        ],
    }

    client = _get_client()
    start = time.perf_counter()
    try:
        response = await client.post(
            MSG91_SMS_URL,
            json=payload,
            headers={
                "authkey": settings.MSG91_API_KEY,
                "Content-Type": "application/json",
            },
        )
    except httpx.RequestError as exc:
        logger.error(
            "sms_network_error",
            ngo_slug=ngo_slug,
            phone_suffix=normalized[-4:],
            error=str(exc),
        )
        return False
    finally:
        elapsed = time.perf_counter() - start
        external_api_latency.labels(service="msg91").observe(elapsed)

    status_code = response.status_code

    if status_code == 200:
        reminders_sent.labels(ngo_slug=ngo_slug, channel="sms").inc()
        logger.info(
            "sms_sent",
            ngo_slug=ngo_slug,
            phone_suffix=normalized[-4:],
            status_code=status_code,
        )
        return True

    if status_code == 429:
        logger.warning(
            "sms_rate_limited",
            ngo_slug=ngo_slug,
            phone_suffix=normalized[-4:],
            status_code=status_code,
        )
        return False

    if status_code in (401, 403):
        # Critical — platform-level misconfiguration, needs immediate attention
        logger.critical(
            "sms_auth_error",
            ngo_slug=ngo_slug,
            status_code=status_code,
            response_body=response.text[:200],
        )
        return False

    # 5xx or other unexpected status
    logger.error(
        "sms_send_failed",
        ngo_slug=ngo_slug,
        phone_suffix=normalized[-4:],
        status_code=status_code,
        response_body=response.text[:200],
    )
    return False


async def send_bulk_sms(
    recipients: list[dict],  # [{"phone": "...", "name": "..."}]
    message_template: str,
    ngo_slug: str,
) -> dict:
    """
    Sends personalised SMS to multiple recipients.
    Returns {"sent": N, "failed": N, "errors": [...]}.
    """
    sent = 0
    failed = 0
    errors: list[str] = []

    async def _send_one(recipient: dict) -> None:
        nonlocal sent, failed
        phone = recipient.get("phone", "")
        name = recipient.get("name", "")
        message = message_template.format(name=name, **{k: v for k, v in recipient.items() if k not in ("phone", "name")})

        # Semaphore caps concurrency — MSG91 free tier limits bulk throughput
        async with _BULK_SEMAPHORE:
            success = await send_sms(phone, message, ngo_slug)

        if success:
            sent += 1
        else:
            failed += 1
            errors.append(f"Failed to send to ...{normalize_phone(phone)[-4:]}")

    await asyncio.gather(*[_send_one(r) for r in recipients])
    return {"sent": sent, "failed": failed, "errors": errors}
