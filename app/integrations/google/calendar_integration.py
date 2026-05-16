"""Google Calendar integration for agent tool use.

Provides read and write access to the NGO's primary Google Calendar.
All blocking API calls are wrapped in asyncio.to_thread().

Use cases:
- List upcoming events: grant deadlines, board meetings, compliance filings
- Create events: reminders for FCRA returns, FC-4 deadlines, donor follow-ups
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.logging import get_logger
from app.core.metrics import google_api_calls

log = get_logger(__name__)

# Calendar ID for the user's primary calendar
_PRIMARY_CALENDAR = "primary"


async def _get_calendar_service(credentials: Credentials):
    """Build a Calendar API v3 service (async-safe via thread offload)."""
    return await asyncio.to_thread(
        build, "calendar", "v3", credentials=credentials, cache_discovery=False
    )


async def list_events(
    credentials: Credentials,
    ngo_slug: str,
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """List calendar events within a time window.

    Args:
        credentials: Valid OAuth2 credentials for the NGO account.
        ngo_slug: For metrics labels.
        time_min: Start of window as ISO 8601 string. Defaults to now.
        time_max: End of window as ISO 8601 string. Defaults to 30 days from now.
        query: Free-text search across event titles and descriptions.
        max_results: Cap on results returned (max 250).

    Returns:
        List of event dicts with keys: id, title, start, end, description, location,
        attendees, organizer, link.
    """
    max_results = min(max_results, 250)
    service = await _get_calendar_service(credentials)

    # Default window: now → 30 days out
    now = datetime.now(timezone.utc)
    if time_min is None:
        time_min = now.isoformat()
    if time_max is None:
        time_max = (now + timedelta(days=30)).isoformat()

    # Ensure RFC 3339 format with timezone suffix
    time_min = _ensure_rfc3339(time_min)
    time_max = _ensure_rfc3339(time_max)

    def _list():
        kwargs: dict[str, Any] = dict(
            calendarId=_PRIMARY_CALENDAR,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,  # expand recurring events
            orderBy="startTime",
        )
        if query:
            kwargs["q"] = query
        return service.events().list(**kwargs).execute()

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="calendar").inc()
        result = await asyncio.to_thread(_list)
    except HttpError as exc:
        _handle_calendar_error(exc, ngo_slug, "list_events")
        raise

    items = result.get("items", [])
    events = [_format_event(item) for item in items]

    log.info(
        "calendar_list_events",
        ngo_slug=ngo_slug,
        event_count=len(events),
    )
    return events


async def create_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    credentials: Credentials,
    ngo_slug: str,
    description: str = "",
    location: str = "",
    attendee_emails: list[str] | None = None,
) -> dict[str, str]:
    """Create a new calendar event on the NGO's primary calendar.

    Args:
        title: Event summary/title.
        start_datetime: ISO 8601 start time (with timezone offset).
        end_datetime: ISO 8601 end time (with timezone offset).
        credentials: Valid OAuth2 credentials.
        ngo_slug: For metrics.
        description: Optional event notes/description.
        location: Optional event location.
        attendee_emails: Optional list of attendee email addresses.

    Returns:
        Dict with id, title, start, end, link.
    """
    service = await _get_calendar_service(credentials)

    start_datetime = _ensure_rfc3339(start_datetime)
    end_datetime = _ensure_rfc3339(end_datetime)

    event_body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_datetime},
        "end": {"dateTime": end_datetime},
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendee_emails:
        event_body["attendees"] = [{"email": e} for e in attendee_emails]

    def _create():
        return (
            service.events()
            .insert(calendarId=_PRIMARY_CALENDAR, body=event_body, sendUpdates="none")
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="calendar").inc()
        result = await asyncio.to_thread(_create)
    except HttpError as exc:
        _handle_calendar_error(exc, ngo_slug, "create_event")
        raise

    event_id = result.get("id", "")
    html_link = result.get("htmlLink", "")

    log.info(
        "calendar_event_created",
        ngo_slug=ngo_slug,
        event_id=event_id,
    )

    return {
        "id": event_id,
        "title": result.get("summary", title),
        "start": start_datetime,
        "end": end_datetime,
        "link": html_link,
        "status": "Event created successfully.",
    }


def _format_event(item: dict) -> dict[str, Any]:
    """Convert a raw Calendar API event dict to a clean agent-friendly format."""
    start = item.get("start", {})
    end = item.get("end", {})
    organizer = item.get("organizer", {})

    # Recurring all-day events use 'date', timed events use 'dateTime'
    start_str = start.get("dateTime") or start.get("date", "")
    end_str = end.get("dateTime") or end.get("date", "")

    return {
        "id": item.get("id", ""),
        "title": item.get("summary", "(no title)"),
        "start": start_str,
        "end": end_str,
        "description": item.get("description", ""),
        "location": item.get("location", ""),
        "attendees": [a.get("email", "") for a in item.get("attendees", [])],
        "organizer": organizer.get("email", ""),
        "link": item.get("htmlLink", ""),
        "status": item.get("status", ""),
    }


def _ensure_rfc3339(dt_str: str) -> str:
    """Normalise a datetime string to RFC 3339 format expected by the Calendar API.

    Handles common input formats:
    - Already RFC 3339: returned as-is.
    - Missing timezone: UTC ('Z') is appended.
    - Date-only 'YYYY-MM-DD': midnight UTC is assumed.
    """
    if not dt_str:
        return datetime.now(timezone.utc).isoformat()

    # Already has a timezone offset
    if "+" in dt_str[10:] or dt_str.endswith("Z"):
        return dt_str

    # Date-only
    if len(dt_str) == 10 and dt_str.count("-") == 2:
        return dt_str + "T00:00:00Z"

    # Assume UTC if no timezone specified
    if "T" in dt_str and not dt_str.endswith("Z"):
        return dt_str + "Z"

    return dt_str


def _handle_calendar_error(exc: HttpError, ngo_slug: str, operation: str) -> None:
    """Structured error logging for Calendar API errors."""
    status = exc.resp.status if exc.resp else 0
    base = dict(ngo_slug=ngo_slug, operation=operation, http_status=status)

    if status == 429:
        log.warning("calendar_quota_exceeded", **base)
    elif status == 403:
        log.error("calendar_permission_denied", **base)
    elif status == 401:
        log.error("calendar_token_expired", **base)
    elif status == 404:
        log.warning("calendar_event_not_found", **base)
    else:
        log.error("calendar_api_error", error=str(exc), **base)
