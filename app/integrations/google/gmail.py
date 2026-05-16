"""Gmail integration for agent tool use.

All operations use the Gmail API v1 via google-api-python-client.
Key design principles:
- Read operations only expose metadata + snippets by default to minimize PII exposure.
- create_draft never sends — it always saves to Drafts so a human reviews before sending.
- asyncio.to_thread() is used for all blocking API calls.
- Errors are surfaced as structured exceptions so the executor can relay them to Claude.
"""

from __future__ import annotations

import asyncio
import base64
import email as stdlib_email
import re
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.logging import get_logger
from app.core.metrics import google_api_calls

log = get_logger(__name__)


async def _get_gmail_service(credentials: Credentials):
    """Build a Gmail API v1 service (async-safe via thread offload)."""
    return await asyncio.to_thread(
        build, "gmail", "v1", credentials=credentials, cache_discovery=False
    )


async def search_emails(
    query: str,
    credentials: Credentials,
    ngo_slug: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search Gmail for messages matching a query string.

    Returns a list of lightweight message summaries (no full body) to keep
    context size manageable. Use get_email() to retrieve the full content.

    Args:
        query: Gmail search query, e.g. "from:donor@example.com subject:grant"
        credentials: Valid OAuth2 credentials for the NGO account.
        ngo_slug: Used for metrics labels only.
        max_results: Maximum messages to return (capped at 50).

    Returns:
        List of dicts with keys: id, thread_id, subject, from, date, snippet.
    """
    max_results = min(max_results, 50)
    service = await _get_gmail_service(credentials)

    def _list():
        return (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="gmail").inc()
        result = await asyncio.to_thread(_list)
    except HttpError as exc:
        _handle_gmail_error(exc, ngo_slug, "search_emails")
        raise

    messages = result.get("messages", [])
    if not messages:
        return []

    # Fetch metadata for each result (subject, from, date, snippet)
    summaries: list[dict[str, Any]] = []
    for msg in messages:
        try:
            summary = await _get_message_metadata(service, msg["id"], ngo_slug)
            summaries.append(summary)
        except HttpError:
            # Skip individual message failures — partial results are better than none
            pass

    log.info(
        "gmail_search",
        ngo_slug=ngo_slug,
        query_length=len(query),  # never log query content — may contain PII
        result_count=len(summaries),
    )
    return summaries


async def _get_message_metadata(service, message_id: str, ngo_slug: str) -> dict[str, Any]:
    """Fetch only the metadata headers and snippet for a single message."""

    def _get():
        return (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "To", "Date"],
            )
            .execute()
        )

    google_api_calls.labels(ngo_slug=ngo_slug, service="gmail").inc()
    msg = await asyncio.to_thread(_get)

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
    }


async def get_email(
    message_id: str,
    credentials: Credentials,
    ngo_slug: str,
) -> dict[str, Any]:
    """Retrieve the full content of a Gmail message by ID.

    The body is decoded from base64 and returned as plain text. HTML bodies
    are stripped to plain text to reduce token consumption.

    Returns:
        Dict with keys: id, subject, from, to, date, body (plain text, max 8KB).
    """
    service = await _get_gmail_service(credentials)

    def _get():
        return (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="gmail").inc()
        msg = await asyncio.to_thread(_get)
    except HttpError as exc:
        _handle_gmail_error(exc, ngo_slug, "get_email")
        raise

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _extract_body(msg.get("payload", {}))

    # Cap body at 8KB to avoid overwhelming the context window
    if len(body) > 8192:
        body = body[:8192] + "\n\n[... message truncated — showing first 8KB ...]"

    log.info("gmail_get_email", ngo_slug=ngo_slug, message_id=message_id)

    return {
        "id": msg["id"],
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a MIME payload structure."""
    mime_type = payload.get("mimeType", "")

    # Direct text/plain part
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return decoded.strip()

    # Prefer text/plain inside multipart; fall back to text/html stripped
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            plain_text = _extract_body(part)
        elif part_mime == "text/html":
            html_text = _strip_html(_extract_body(part))
        elif part_mime.startswith("multipart/"):
            nested = _extract_body(part)
            if nested:
                plain_text = nested

    if plain_text:
        return plain_text
    if html_text:
        return html_text

    # Last resort: decode whatever body is present
    data = payload.get("body", {}).get("data", "")
    if data:
        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        if mime_type == "text/html":
            return _strip_html(decoded)
        return decoded.strip()

    return ""


def _strip_html(html: str) -> str:
    """Very basic HTML tag stripping — sufficient for email body previews."""
    # Remove script and style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Decode common HTML entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return text


async def create_draft(
    to: str,
    subject: str,
    body: str,
    credentials: Credentials,
    ngo_slug: str,
    reply_to_message_id: str | None = None,
) -> dict[str, str]:
    """Create a Gmail draft (does NOT send it).

    The draft is saved to the NGO's Gmail Drafts folder. Staff must open
    Gmail to review and send it. This is intentional — agents should never
    send email autonomously.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.
        credentials: Valid OAuth2 credentials.
        ngo_slug: For metrics.
        reply_to_message_id: If set, the draft will be a reply in that thread.

    Returns:
        Dict with id and message_id of the created draft.
    """
    service = await _get_gmail_service(credentials)

    # Build a MIME message
    mime_msg = MIMEText(body, "plain", "utf-8")
    mime_msg["to"] = to
    mime_msg["subject"] = subject

    if reply_to_message_id:
        mime_msg["In-Reply-To"] = reply_to_message_id
        mime_msg["References"] = reply_to_message_id

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")

    draft_body: dict[str, Any] = {"message": {"raw": raw}}
    if reply_to_message_id:
        draft_body["message"]["threadId"] = reply_to_message_id

    def _create():
        return service.users().drafts().create(userId="me", body=draft_body).execute()

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="gmail").inc()
        result = await asyncio.to_thread(_create)
    except HttpError as exc:
        _handle_gmail_error(exc, ngo_slug, "create_draft")
        raise

    draft_id = result.get("id", "")
    message_id = result.get("message", {}).get("id", "")

    log.info(
        "gmail_draft_created",
        ngo_slug=ngo_slug,
        draft_id=draft_id,
        # Never log to/subject — may contain PII or sensitive info
    )

    return {
        "draft_id": draft_id,
        "message_id": message_id,
        "status": "Draft saved. Open Gmail Drafts to review and send.",
    }


def _handle_gmail_error(exc: HttpError, ngo_slug: str, operation: str) -> None:
    """Structured error logging for Gmail API errors."""
    status = exc.resp.status if exc.resp else 0
    base = dict(ngo_slug=ngo_slug, operation=operation, http_status=status)

    if status == 429:
        log.warning("gmail_quota_exceeded", **base)
    elif status == 403:
        log.error("gmail_permission_denied", **base)
    elif status == 401:
        log.error("gmail_token_expired", **base)
    elif status == 404:
        log.warning("gmail_message_not_found", **base)
    else:
        log.error("gmail_api_error", error=str(exc), **base)
