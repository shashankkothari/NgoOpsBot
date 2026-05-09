from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import external_api_latency, reminders_sent

if TYPE_CHECKING:
    from app.models.ngo import NGO

logger = get_logger(__name__)
settings = get_settings()

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

# Platform send-from address — constant so SPF/DKIM records are stable
_FROM_EMAIL = "ngoopsbot@ngoopsbot.com"

# Module-level client — reuses TLS sessions across all email sends
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # Generous timeout: SendGrid occasionally batches before acknowledging
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


def mask_email(email: str) -> str:
    # Avoids PII in logs while still providing enough to debug delivery issues
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    return f"{parts[0]}@***.{parts[1].split('.')[-1]}"


def text_to_html(text: str) -> str:
    # Minimal conversion — avoids a heavy templating dependency for simple emails
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Wrap URLs in anchor tags so they're clickable in email clients
    url_pattern = r"(https?://[^\s]+)"
    linked = re.sub(url_pattern, r'<a href="\1">\1</a>', escaped)
    # Newlines to <br> last so URL linking doesn't corrupt the anchors
    return linked.replace("\n", "<br>\n")


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    ngo: "NGO",
    cc: Optional[list[str]] = None,
) -> bool:
    """
    Sends transactional email via SendGrid.
    Returns True on success (202 Accepted), False on failure.
    """
    from_name = f"{ngo.name} (via NGO OpsBot)"

    payload: dict = {
        "personalizations": [
            {
                "to": [{"email": to_email, "name": to_name}],
                **({"cc": [{"email": addr} for addr in cc]} if cc else {}),
            }
        ],
        "from": {"email": _FROM_EMAIL, "name": from_name},
        "reply_to": {"email": _FROM_EMAIL, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body},
            {"type": "text/html", "value": text_to_html(body)},
        ],
    }

    client = _get_client()
    start = time.perf_counter()
    try:
        response = await client.post(
            SENDGRID_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    except httpx.RequestError as exc:
        logger.error(
            "email_network_error",
            ngo_slug=ngo.slug,
            to_email=mask_email(to_email),
            error=str(exc),
        )
        return False
    finally:
        elapsed = time.perf_counter() - start
        external_api_latency.labels(service="sendgrid").observe(elapsed)

    status_code = response.status_code

    # SendGrid signals success with 202 Accepted — no response body to parse
    if status_code == 202:
        reminders_sent.labels(ngo_slug=ngo.slug, channel="email").inc()
        logger.info(
            "email_sent",
            ngo_slug=ngo.slug,
            to_email=mask_email(to_email),
            subject=subject[:50],
            status_code=status_code,
        )
        return True

    if status_code == 429:
        logger.warning(
            "email_rate_limited",
            ngo_slug=ngo.slug,
            to_email=mask_email(to_email),
            status_code=status_code,
        )
        return False

    if status_code in (401, 403):
        # Critical — bad API key blocks all outbound email for this NGO
        logger.critical(
            "email_auth_error",
            ngo_slug=ngo.slug,
            status_code=status_code,
            response_body=response.text[:200],
        )
        return False

    # 5xx or unexpected
    logger.error(
        "email_send_failed",
        ngo_slug=ngo.slug,
        to_email=mask_email(to_email),
        subject=subject[:50],
        status_code=status_code,
        response_body=response.text[:200],
    )
    return False


async def send_bulk_email(
    recipients: list[dict],  # [{"email": "...", "name": "...", "context": {...}}]
    subject: str,
    body_template: str,
    ngo: "NGO",
) -> dict:
    """
    Sends personalised emails using SendGrid Personalizations — one API call
    for up to 1000 recipients, which is a single rate-limit hit and better
    deliverability than looping individual calls.
    Returns {"sent": N, "failed": N}.
    """
    if not recipients:
        return {"sent": 0, "failed": 0}

    # Build per-recipient substitutions inside Personalizations
    personalizations = []
    for r in recipients:
        ctx = r.get("context", {})
        body = body_template.format(name=r.get("name", ""), **ctx)
        personalizations.append({
            "to": [{"email": r["email"], "name": r.get("name", "")}],
            # Substitution variables are per-personalization in SendGrid v3
            "dynamic_template_data": {"body": body, "subject": subject},
        })

    # SendGrid caps personalizations at 1000 per call — chunk if needed
    CHUNK_SIZE = 1000
    total_sent = 0
    total_failed = 0

    for i in range(0, len(personalizations), CHUNK_SIZE):
        chunk = personalizations[i : i + CHUNK_SIZE]
        # Use first recipient's body for the canonical content block
        first_body = body_template.format(
            name=recipients[i].get("name", ""),
            **recipients[i].get("context", {}),
        )

        payload = {
            "personalizations": chunk,
            "from": {
                "email": _FROM_EMAIL,
                "name": f"{ngo.name} (via NGO OpsBot)",
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": first_body},
                {"type": "text/html", "value": text_to_html(first_body)},
            ],
        }

        client = _get_client()
        start = time.perf_counter()
        try:
            response = await client.post(
                SENDGRID_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.RequestError as exc:
            logger.error(
                "bulk_email_network_error",
                ngo_slug=ngo.slug,
                chunk_size=len(chunk),
                error=str(exc),
            )
            total_failed += len(chunk)
            continue
        finally:
            elapsed = time.perf_counter() - start
            external_api_latency.labels(service="sendgrid").observe(elapsed)

        if response.status_code == 202:
            total_sent += len(chunk)
            reminders_sent.labels(ngo_slug=ngo.slug, channel="email").inc(len(chunk))
        elif response.status_code in (401, 403):
            logger.critical(
                "bulk_email_auth_error",
                ngo_slug=ngo.slug,
                status_code=response.status_code,
            )
            total_failed += len(chunk)
        else:
            logger.error(
                "bulk_email_chunk_failed",
                ngo_slug=ngo.slug,
                status_code=response.status_code,
                chunk_size=len(chunk),
                response_body=response.text[:200],
            )
            total_failed += len(chunk)

    return {"sent": total_sent, "failed": total_failed}
