"""Anthropic tool definitions (JSON schemas) for all agent tools.

Each entry is a dict matching the Anthropic tools API format:
  {"name": str, "description": str, "input_schema": {...}}

Per-agent tool lists are defined at the bottom. Agents reference their
tool names; get_tool_definitions() resolves names to full schemas.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Individual tool definitions
# ---------------------------------------------------------------------------

_CALCULATOR = {
    "name": "calculator",
    "description": (
        "Evaluate a mathematical expression safely. Use this for any arithmetic: "
        "budget variances, grant utilisation percentages, TDS calculations, "
        "donation totals, financial ratios, etc. "
        "Supported: +, -, *, /, //, %, ** and functions: abs, round, min, max, "
        "sum, sqrt, ceil, floor, log, log10, pow."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "A mathematical expression to evaluate. "
                    "Examples: '50000 * 0.10', 'round(125000 / 365, 2)', "
                    "'min(500000, 480000) / 500000 * 100'"
                ),
            }
        },
        "required": ["expression"],
    },
}

_WEB_SEARCH = {
    "name": "web_search",
    "description": (
        "Search the web for current information. Use for: regulatory updates "
        "(FCRA rules, TDS rates, CSR schedules), NGO compliance deadlines, "
        "grant opportunities, funder profiles, sector benchmarks, or any "
        "topic where up-to-date external information is needed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The search query. Be specific. "
                    "Good: 'FCRA annual return FC-4 due date India 2024'. "
                    "Less good: 'FCRA'."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5, max: 20).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

_READ_SHEET_TAB = {
    "name": "read_sheet_tab",
    "description": (
        "Read all rows from a tab in the NGO's Google Sheets Master Tracker. "
        "Returns a JSON list of row objects, each keyed by column header. "
        "Use this before any analysis that requires actual NGO data: donor lists, "
        "grant status, finance figures, staff records."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tab_name": {
                "type": "string",
                "description": "Name of the tab to read.",
                "enum": ["Donors", "Grants", "Finance", "Staff", "Reminders"],
            }
        },
        "required": ["tab_name"],
    },
}

_APPEND_SHEET_ROW = {
    "name": "append_sheet_row",
    "description": (
        "Append a new row to a tab in the NGO's Master Tracker. "
        "Use to add a new donor, grant, expense entry, staff record, or reminder. "
        "Column names must match the tab's defined headers exactly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tab_name": {
                "type": "string",
                "description": "Name of the tab.",
                "enum": ["Donors", "Grants", "Finance", "Staff", "Reminders"],
            },
            "row_data": {
                "type": "object",
                "description": (
                    "Key-value pairs matching the tab's column headers. "
                    "Donors headers: Name, Email, Phone, Last Gift Date, Last Gift Amount, "
                    "Total Given, Status, Notes. "
                    "Grants headers: Grant Name, Funder, Amount, Status, Application Date, "
                    "Decision Date, Reporting Deadline, Utilization %, Notes. "
                    "Finance headers: Month, Category, Budget, Actual, Variance, Notes. "
                    "Staff headers: Name, Role, Join Date, Leave Balance, Phone, Email, Status. "
                    "Reminders headers: Title, Type, Due Date, Status, Assigned To, Notes."
                ),
            },
        },
        "required": ["tab_name", "row_data"],
    },
}

_FIND_AND_UPDATE_SHEET_ROW = {
    "name": "find_and_update_sheet_row",
    "description": (
        "Find the first row where a specific column equals a given value, "
        "then update fields in that row. Use this to update an existing record: "
        "mark a grant as closed, update a donor's last gift date, change a "
        "staff member's leave balance, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tab_name": {
                "type": "string",
                "description": "Name of the tab.",
                "enum": ["Donors", "Grants", "Finance", "Staff", "Reminders"],
            },
            "match_column": {
                "type": "string",
                "description": "Column header to match against (e.g. 'Name', 'Grant Name').",
            },
            "match_value": {
                "type": "string",
                "description": "Value to search for in match_column.",
            },
            "updates": {
                "type": "object",
                "description": (
                    "Key-value pairs of columns to update in the matched row. "
                    "Unspecified columns are left unchanged."
                ),
            },
        },
        "required": ["tab_name", "match_column", "match_value", "updates"],
    },
}

_SEARCH_EMAILS = {
    "name": "search_emails",
    "description": (
        "Search the NGO's Gmail for emails matching a query. "
        "Returns message summaries (subject, from, date, snippet) — "
        "not full bodies. Use get_email to retrieve the full content of a specific message. "
        "Useful for finding grant communications, donor correspondence, invoices, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Gmail search query. Examples: "
                    "'from:donor@example.com', "
                    "'subject:grant report utilisation', "
                    "'after:2024/01/01 before:2024/06/30 invoice', "
                    "'label:important funder'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return (default: 10, max: 50).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

_GET_EMAIL = {
    "name": "get_email",
    "description": (
        "Retrieve the full content of a Gmail message by its ID. "
        "Call search_emails first to find the message ID, then use this "
        "to read the complete email body."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID from search_emails results.",
            }
        },
        "required": ["message_id"],
    },
}

_CREATE_EMAIL_DRAFT = {
    "name": "create_email_draft",
    "description": (
        "Create a Gmail draft (DOES NOT SEND). The draft is saved to the "
        "Gmail Drafts folder for the staff member to review and send manually. "
        "Use for: donor thank-you notes, grant application follow-ups, "
        "re-engagement emails, board communications, volunteer outreach."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address.",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text). Format clearly with paragraphs.",
            },
            "reply_to_message_id": {
                "type": "string",
                "description": (
                    "Optional. Gmail message ID to reply to. "
                    "Sets In-Reply-To header to thread the draft with an existing conversation."
                ),
            },
        },
        "required": ["to", "subject", "body"],
    },
}

_LIST_CALENDAR_EVENTS = {
    "name": "list_calendar_events",
    "description": (
        "List upcoming events from the NGO's Google Calendar. "
        "Use to check schedules, upcoming deadlines, board meetings, "
        "grant reporting dates, compliance filing dates, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "time_min": {
                "type": "string",
                "description": (
                    "Start of the time window as ISO 8601 string "
                    "(e.g. '2024-06-01T00:00:00Z'). Defaults to now."
                ),
            },
            "time_max": {
                "type": "string",
                "description": (
                    "End of the time window as ISO 8601 string. "
                    "Defaults to 30 days from now."
                ),
            },
            "query": {
                "type": "string",
                "description": "Optional free-text search within event titles and descriptions.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default: 20, max: 250).",
                "default": 20,
            },
        },
        "required": [],
    },
}

_CREATE_CALENDAR_EVENT = {
    "name": "create_calendar_event",
    "description": (
        "Create a new event on the NGO's Google Calendar. "
        "Use for: grant reporting deadlines, board meeting reminders, "
        "FCRA/compliance filing dates, donor follow-up calls, "
        "volunteer orientation sessions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title/summary (e.g. 'FCRA Annual Return FC-4 Deadline').",
            },
            "start_datetime": {
                "type": "string",
                "description": (
                    "Start date/time as ISO 8601 string with timezone offset. "
                    "Example: '2024-12-31T09:00:00+05:30' for IST. "
                    "For all-day events use 'YYYY-MM-DD' format."
                ),
            },
            "end_datetime": {
                "type": "string",
                "description": (
                    "End date/time as ISO 8601 string. "
                    "For reminders with no specific end time, set 1 hour after start."
                ),
            },
            "description": {
                "type": "string",
                "description": "Optional event notes (what needs to be done, links, contacts).",
            },
            "location": {
                "type": "string",
                "description": "Optional location or video call link.",
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of attendee email addresses. sendUpdates is set to 'none' so no invites are sent.",
            },
        },
        "required": ["title", "start_datetime", "end_datetime"],
    },
}

# ---------------------------------------------------------------------------
# Registry: name → definition
# ---------------------------------------------------------------------------

ALL_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "calculator": _CALCULATOR,
    "web_search": _WEB_SEARCH,
    "read_sheet_tab": _READ_SHEET_TAB,
    "append_sheet_row": _APPEND_SHEET_ROW,
    "find_and_update_sheet_row": _FIND_AND_UPDATE_SHEET_ROW,
    "search_emails": _SEARCH_EMAILS,
    "get_email": _GET_EMAIL,
    "create_email_draft": _CREATE_EMAIL_DRAFT,
    "list_calendar_events": _LIST_CALENDAR_EVENTS,
    "create_calendar_event": _CREATE_CALENDAR_EVENT,
}

# ---------------------------------------------------------------------------
# Per-agent tool sets
# ---------------------------------------------------------------------------

# Tools available to each agent by name.
# Agents access real data only if the NGO has completed the OAuth flow.
# Google-dependent tools fail gracefully with an auth error message if not connected.

AGENT_TOOLS: dict[str, list[str]] = {
    "fundraising": [
        "calculator",
        "web_search",
        "read_sheet_tab",
        "append_sheet_row",
        "find_and_update_sheet_row",
        "search_emails",
        "get_email",
        "create_email_draft",
    ],
    "finance": [
        "calculator",
        "web_search",
        "read_sheet_tab",
        "append_sheet_row",
        "find_and_update_sheet_row",
    ],
    "hr": [
        "calculator",
        "web_search",
        "read_sheet_tab",
        "append_sheet_row",
        "find_and_update_sheet_row",
        "search_emails",
        "get_email",
        "create_email_draft",
    ],
    "marketing": [
        "calculator",
        "web_search",
        "search_emails",
        "get_email",
        "create_email_draft",
    ],
    "compliance": [
        "calculator",
        "web_search",
        "read_sheet_tab",
        "list_calendar_events",
        "create_calendar_event",
    ],
    "general": list(ALL_TOOL_DEFINITIONS.keys()),  # all tools
    "comms": [
        "calculator",
        "web_search",
        "search_emails",
        "get_email",
        "create_email_draft",
        "list_calendar_events",
        "create_calendar_event",
    ],
}


def get_tool_definitions(tool_names: list[str]) -> list[dict[str, Any]]:
    """Resolve a list of tool names to their full Anthropic tool definition dicts.

    Unknown names are silently skipped (logged at debug level).
    """
    definitions = []
    for name in tool_names:
        defn = ALL_TOOL_DEFINITIONS.get(name)
        if defn is not None:
            definitions.append(defn)
    return definitions
