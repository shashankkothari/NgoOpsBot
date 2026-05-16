"""Tool executor — routes Claude tool_use calls to their implementations.

The executor is the bridge between the Anthropic tool-use protocol and the
actual Python functions that do the work. It:
1. Receives a tool name and input dict from Claude's response.
2. Validates that the tool is in our registry.
3. Executes the appropriate function, injecting context (NGO, DB, credentials).
4. Returns a string result to be sent back as a tool_result message.

All errors are caught and returned as descriptive strings prefixed with
"Error:" so Claude can communicate the failure to the user rather than
crashing the conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ngo import NGO
    from app.models.staff import Staff

log = get_logger(__name__)


@dataclass
class ToolContext:
    """Contextual data available to all tool implementations.

    Populated from the agent's invoke() call and passed through _call_claude.
    None values indicate the relevant service is unavailable for this request.
    """

    ngo: "NGO"
    staff: "Staff | None" = None
    db: "AsyncSession | None" = None
    # Cached credentials — fetched once per agent turn if Google tools are needed
    _google_credentials: Any = None


async def _get_google_credentials(ctx: ToolContext) -> Any:
    """Lazily fetch and cache Google credentials for this turn.

    Returns None if the NGO hasn't connected Google, raising a user-friendly error.
    """
    if ctx._google_credentials is not None:
        return ctx._google_credentials

    from app.integrations.google.credentials_manager import (
        GoogleAuthError,
        get_valid_credentials,
    )

    if ctx.db is None:
        raise RuntimeError("Database session unavailable — cannot fetch Google credentials.")

    try:
        creds = await get_valid_credentials(ctx.ngo, ctx.db)
    except GoogleAuthError as exc:
        raise RuntimeError(str(exc)) from exc

    ctx._google_credentials = creds
    return creds


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

async def _run_calculator(input_data: dict, ctx: ToolContext) -> str:
    from app.agents.tools.calculator import calculate

    expression = input_data.get("expression", "")
    if not expression:
        return "Error: 'expression' parameter is required."
    try:
        return calculate(expression)
    except ValueError as exc:
        return f"Error: {exc}"


async def _run_web_search(input_data: dict, ctx: ToolContext) -> str:
    from app.agents.tools.web_search import web_search

    query = input_data.get("query", "")
    if not query:
        return "Error: 'query' parameter is required."
    max_results = int(input_data.get("max_results", 5))
    return await web_search(query, max_results=max_results)


async def _run_read_sheet_tab(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.sheets import read_tab

    tab_name = input_data.get("tab_name", "")
    if not tab_name:
        return "Error: 'tab_name' parameter is required."

    if not ctx.ngo.google_spreadsheet_id:
        return (
            "Error: This NGO has not set up a Google Sheets Master Tracker. "
            "Connect Google from the admin dashboard and run the onboarding flow first."
        )

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        rows = await read_tab(
            spreadsheet_id=ctx.ngo.google_spreadsheet_id,
            tab_name=tab_name,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
        )
    except Exception as exc:
        return f"Error reading '{tab_name}' tab: {exc}"

    if not rows:
        return f"The '{tab_name}' tab is empty — no data found."

    return json.dumps(rows, ensure_ascii=False, indent=2)


async def _run_append_sheet_row(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.sheets import append_row

    tab_name = input_data.get("tab_name", "")
    row_data = input_data.get("row_data", {})

    if not tab_name:
        return "Error: 'tab_name' parameter is required."
    if not row_data:
        return "Error: 'row_data' parameter is required and must be non-empty."

    if not ctx.ngo.google_spreadsheet_id:
        return (
            "Error: No Google Sheets Master Tracker configured for this NGO. "
            "Connect Google from the admin dashboard first."
        )

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        row_number = await append_row(
            spreadsheet_id=ctx.ngo.google_spreadsheet_id,
            tab_name=tab_name,
            row_data=row_data,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
        )
    except Exception as exc:
        return f"Error appending row to '{tab_name}': {exc}"

    return f"Row appended successfully to '{tab_name}' (data row #{row_number})."


async def _run_find_and_update_sheet_row(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.sheets import find_and_update_row

    tab_name = input_data.get("tab_name", "")
    match_column = input_data.get("match_column", "")
    match_value = input_data.get("match_value", "")
    updates = input_data.get("updates", {})

    if not all([tab_name, match_column, match_value]):
        return "Error: 'tab_name', 'match_column', and 'match_value' are all required."
    if not updates:
        return "Error: 'updates' must be non-empty."

    if not ctx.ngo.google_spreadsheet_id:
        return (
            "Error: No Google Sheets Master Tracker configured for this NGO. "
            "Connect Google from the admin dashboard first."
        )

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        found = await find_and_update_row(
            spreadsheet_id=ctx.ngo.google_spreadsheet_id,
            tab_name=tab_name,
            match_column=match_column,
            match_value=match_value,
            updates=updates,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
        )
    except Exception as exc:
        return f"Error updating row in '{tab_name}': {exc}"

    if not found:
        return (
            f"No row found in '{tab_name}' where '{match_column}' = '{match_value}'. "
            "Use append_sheet_row to add a new entry instead."
        )
    return f"Row updated successfully in '{tab_name}' (matched on {match_column} = '{match_value}')."


async def _run_search_emails(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.gmail import search_emails

    query = input_data.get("query", "")
    if not query:
        return "Error: 'query' parameter is required."
    max_results = int(input_data.get("max_results", 10))

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        messages = await search_emails(
            query=query,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
            max_results=max_results,
        )
    except Exception as exc:
        return f"Error searching emails: {exc}"

    if not messages:
        return f"No emails found matching: {query}"

    lines = [f"Found {len(messages)} email(s):\n"]
    for msg in messages:
        lines.append(
            f"ID: {msg['id']}\n"
            f"  From: {msg['from']}\n"
            f"  Subject: {msg['subject']}\n"
            f"  Date: {msg['date']}\n"
            f"  Snippet: {msg['snippet']}"
        )
    return "\n\n".join(lines)


async def _run_get_email(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.gmail import get_email

    message_id = input_data.get("message_id", "")
    if not message_id:
        return "Error: 'message_id' parameter is required."

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        email = await get_email(
            message_id=message_id,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
        )
    except Exception as exc:
        return f"Error retrieving email {message_id}: {exc}"

    return (
        f"From: {email['from']}\n"
        f"To: {email['to']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date']}\n"
        f"\n{email['body']}"
    )


async def _run_create_email_draft(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.gmail import create_draft

    to = input_data.get("to", "")
    subject = input_data.get("subject", "")
    body = input_data.get("body", "")
    reply_to = input_data.get("reply_to_message_id")

    if not to or not subject or not body:
        return "Error: 'to', 'subject', and 'body' are all required."

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        result = await create_draft(
            to=to,
            subject=subject,
            body=body,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
            reply_to_message_id=reply_to,
        )
    except Exception as exc:
        return f"Error creating draft: {exc}"

    return (
        f"Draft created successfully.\n"
        f"Draft ID: {result['draft_id']}\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"Status: {result['status']}\n"
        f"Note: The staff member must open Gmail Drafts to review and send this email."
    )


async def _run_list_calendar_events(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.calendar_integration import list_events

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        events = await list_events(
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
            time_min=input_data.get("time_min"),
            time_max=input_data.get("time_max"),
            query=input_data.get("query"),
            max_results=int(input_data.get("max_results", 20)),
        )
    except Exception as exc:
        return f"Error listing calendar events: {exc}"

    if not events:
        return "No upcoming calendar events found in the specified time range."

    lines = [f"Found {len(events)} event(s):\n"]
    for ev in events:
        lines.append(
            f"• {ev['title']}\n"
            f"  Start: {ev['start']}\n"
            f"  End: {ev['end']}"
            + (f"\n  Description: {ev['description'][:200]}" if ev.get("description") else "")
            + (f"\n  Link: {ev['link']}" if ev.get("link") else "")
        )
    return "\n\n".join(lines)


async def _run_create_calendar_event(input_data: dict, ctx: ToolContext) -> str:
    from app.integrations.google.calendar_integration import create_event

    title = input_data.get("title", "")
    start = input_data.get("start_datetime", "")
    end = input_data.get("end_datetime", "")

    if not title or not start or not end:
        return "Error: 'title', 'start_datetime', and 'end_datetime' are all required."

    try:
        creds = await _get_google_credentials(ctx)
    except RuntimeError as exc:
        return f"Error: {exc}"

    try:
        result = await create_event(
            title=title,
            start_datetime=start,
            end_datetime=end,
            credentials=creds,
            ngo_slug=ctx.ngo.slug,
            description=input_data.get("description", ""),
            location=input_data.get("location", ""),
            attendee_emails=input_data.get("attendees", []),
        )
    except Exception as exc:
        return f"Error creating calendar event: {exc}"

    return (
        f"Calendar event created successfully.\n"
        f"Title: {result['title']}\n"
        f"Start: {result['start']}\n"
        f"End: {result['end']}\n"
        + (f"Link: {result['link']}\n" if result.get("link") else "")
        + f"Status: {result['status']}"
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_TOOL_HANDLERS: dict[str, Any] = {
    "calculator": _run_calculator,
    "web_search": _run_web_search,
    "read_sheet_tab": _run_read_sheet_tab,
    "append_sheet_row": _run_append_sheet_row,
    "find_and_update_sheet_row": _run_find_and_update_sheet_row,
    "search_emails": _run_search_emails,
    "get_email": _run_get_email,
    "create_email_draft": _run_create_email_draft,
    "list_calendar_events": _run_list_calendar_events,
    "create_calendar_event": _run_create_calendar_event,
}


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    ctx: ToolContext,
) -> str:
    """Execute a tool by name with the given input and context.

    Returns a string result (always — errors are returned as "Error: ..." strings
    so Claude can relay them to the user rather than crashing the conversation).

    Args:
        tool_name: Name matching an entry in ALL_TOOL_DEFINITIONS.
        tool_input: Input dict as provided by Claude (matches the tool's input_schema).
        ctx: Context providing NGO, staff, and DB session.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        log.warning("tool_unknown", tool_name=tool_name)
        return f"Error: Unknown tool '{tool_name}'. This is a configuration issue."

    log.info("tool_executing", tool_name=tool_name, ngo_slug=ctx.ngo.slug)

    try:
        result = await handler(tool_input, ctx)
        log.info(
            "tool_completed",
            tool_name=tool_name,
            ngo_slug=ctx.ngo.slug,
            result_length=len(str(result)),
        )
        return result
    except Exception as exc:
        # Catch-all: unexpected errors should not crash the conversation
        log.error(
            "tool_unexpected_error",
            tool_name=tool_name,
            ngo_slug=ctx.ngo.slug,
            error=str(exc),
        )
        return f"Error: Unexpected error running {tool_name}: {exc}"
