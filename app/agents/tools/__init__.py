"""Agent tool infrastructure.

Tools give agents the ability to take real actions beyond conversation:
- calculator: safe arithmetic for financial calculations
- web_search: search the web for current information
- read_sheet_tab / append_sheet_row / find_and_update_sheet_row: Google Sheets
- search_emails / get_email / create_email_draft: Gmail
- list_calendar_events / create_calendar_event: Google Calendar

Usage: import from app.agents.tools.definitions and app.agents.tools.executor.
"""

from app.agents.tools.definitions import ALL_TOOL_DEFINITIONS, get_tool_definitions
from app.agents.tools.executor import ToolContext, execute_tool

__all__ = [
    "ALL_TOOL_DEFINITIONS",
    "get_tool_definitions",
    "ToolContext",
    "execute_tool",
]
