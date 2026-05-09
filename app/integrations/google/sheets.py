"""Google Sheets operations for the NGO Master Tracker.

The Master Tracker is one spreadsheet per NGO with one tab per operational domain.
Each agent owns its tab exclusively, preventing cross-agent data corruption.
All API calls are wrapped in asyncio.to_thread() because google-api-python-client
is synchronous and would block the event loop otherwise.
"""

from __future__ import annotations

import asyncio
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.logging import get_logger
from app.core.metrics import google_api_calls

log = get_logger(__name__)

# Tab definitions: name → ordered list of column headers
# Header order is canonical — agents must use these exact names as dict keys
TAB_HEADERS: dict[str, list[str]] = {
    "Donors": [
        "Name", "Email", "Phone", "Last Gift Date", "Last Gift Amount",
        "Total Given", "Status", "Notes",
    ],
    "Grants": [
        "Grant Name", "Funder", "Amount", "Status", "Application Date",
        "Decision Date", "Reporting Deadline", "Utilization %", "Notes",
    ],
    "Finance": ["Month", "Category", "Budget", "Actual", "Variance", "Notes"],
    "Staff": ["Name", "Role", "Join Date", "Leave Balance", "Phone", "Email", "Status"],
    "Reminders": ["Title", "Type", "Due Date", "Status", "Assigned To", "Notes"],
}

# Per-tab background colors for header rows — visually separates domains
_TAB_COLORS: dict[str, dict] = {
    "Donors":    {"red": 0.91, "green": 0.73, "blue": 0.73},  # warm red
    "Grants":    {"red": 0.73, "green": 0.87, "blue": 0.73},  # soft green
    "Finance":   {"red": 0.73, "green": 0.80, "blue": 0.91},  # calm blue
    "Staff":     {"red": 0.98, "green": 0.91, "blue": 0.73},  # amber
    "Reminders": {"red": 0.87, "green": 0.78, "blue": 0.91},  # lavender
}

_SHEET_MIME = "application/vnd.google-apps.spreadsheet"


async def get_sheets_service(credentials: Credentials):
    """Build a Sheets API v4 service, wrapped for async use.

    cache_discovery=False avoids writing a discovery doc cache to disk,
    which can cause permission issues in containerised deployments.
    """
    return await asyncio.to_thread(
        build, "sheets", "v4", credentials=credentials, cache_discovery=False
    )


async def create_master_tracker(
    folder_id: str,
    credentials: Credentials,
    ngo_name: str,
) -> str:
    """Create the Master Tracker spreadsheet inside the NGO's Drive folder.

    Returns spreadsheet_id.  Tabs and headers are added by setup_master_tracker
    after creation so that step can also be called independently on repair runs.
    """
    # Use Drive API to create the sheet file so we can specify the parent folder
    from app.integrations.google.drive import get_drive_service
    drive_service = await get_drive_service(credentials)
    title = f"NGO OpsBot Master Tracker — {ngo_name}"

    def _create():
        return (
            drive_service.files()
            .create(
                body={
                    "name": title,
                    "mimeType": _SHEET_MIME,
                    "parents": [folder_id],
                },
                fields="id",
            )
            .execute()
        )

    result = await asyncio.to_thread(_create)
    spreadsheet_id = result["id"]
    log.info("google_sheets_created", spreadsheet_id=spreadsheet_id, ngo_name=ngo_name)

    # Populate tabs and headers immediately after creation
    await setup_master_tracker(spreadsheet_id, credentials)
    return spreadsheet_id


async def setup_master_tracker(
    spreadsheet_id: str,
    credentials: Credentials,
) -> None:
    """Ensure all required tabs exist with headers, formatting applied.

    Idempotent — skips tabs that already exist so reconnects don't wipe data.
    Formatting uses batchUpdate to minimize round trips.
    """
    service = await get_sheets_service(credentials)

    # Fetch current sheet structure to know which tabs need to be created
    def _get_meta():
        return (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
            .execute()
        )

    meta = await asyncio.to_thread(_get_meta)
    existing_tabs = {
        s["properties"]["title"] for s in meta.get("sheets", [])
    }
    # Sheet1 is the default tab created with every new spreadsheet
    default_tab = next(
        (
            s["properties"]
            for s in meta.get("sheets", [])
            if s["properties"]["title"] == "Sheet1"
        ),
        None,
    )

    requests: list[dict] = []

    # Rename the default Sheet1 to our first tab instead of deleting + creating
    first_tab = next(iter(TAB_HEADERS))
    if "Sheet1" in existing_tabs and first_tab not in existing_tabs:
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": default_tab["sheetId"],
                    "title": first_tab,
                },
                "fields": "title",
            }
        })
        existing_tabs.discard("Sheet1")
        existing_tabs.add(first_tab)

    # Add any missing tabs
    for tab_name in TAB_HEADERS:
        if tab_name not in existing_tabs:
            requests.append({"addSheet": {"properties": {"title": tab_name}}})

    if requests:
        def _batch(reqs):
            return (
                service.spreadsheets()
                .batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": reqs},
                )
                .execute()
            )
        await asyncio.to_thread(_batch, requests)
        log.info(
            "google_sheets_tabs_created",
            spreadsheet_id=spreadsheet_id,
            tabs_created=len(requests),
        )

    # Write headers and apply formatting for each tab
    await _write_headers_and_format(spreadsheet_id, service, credentials)


async def _write_headers_and_format(
    spreadsheet_id: str,
    service,
    credentials: Credentials,
) -> None:
    """Write header rows and apply bold + freeze + background color formatting.

    Batches header writes and format requests together to reduce API quota usage.
    """
    # Fetch updated sheet IDs now that new tabs have been added
    def _get_meta():
        return (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
            .execute()
        )

    meta = await asyncio.to_thread(_get_meta)
    sheet_id_map = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in meta.get("sheets", [])
    }

    value_ranges = []
    format_requests = []

    for tab_name, headers in TAB_HEADERS.items():
        if tab_name not in sheet_id_map:
            continue
        sheet_id = sheet_id_map[tab_name]
        col_count = len(headers)

        # Write the header row values
        value_ranges.append({
            "range": f"'{tab_name}'!A1",
            "values": [headers],
        })

        # Bold header cells
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": _TAB_COLORS.get(tab_name, {}),
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })

        # Freeze the header row so scrolling doesn't lose column context
        format_requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })

    def _values_update():
        return (
            service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": value_ranges,
                },
            )
            .execute()
        )

    def _format_update():
        return (
            service.spreadsheets()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": format_requests},
            )
            .execute()
        )

    await asyncio.to_thread(_values_update)
    await asyncio.to_thread(_format_update)
    log.info(
        "google_sheets_headers_written",
        spreadsheet_id=spreadsheet_id,
        tab_count=len(TAB_HEADERS),
    )


async def read_tab(
    spreadsheet_id: str,
    tab_name: str,
    credentials: Credentials,
    ngo_slug: str,
) -> list[dict]:
    """Read all rows from a tab, returning each as a dict keyed by header.

    Empty sheets return [].  Rows with fewer columns than headers are padded
    with empty strings so downstream code can safely access all keys.
    """
    service = await get_sheets_service(credentials)
    range_name = f"'{tab_name}'!A:ZZ"

    def _read():
        return (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="sheets").inc()
        result = await asyncio.to_thread(_read)
    except HttpError as exc:
        _handle_sheets_error(exc, ngo_slug, "read_tab", spreadsheet_id, tab_name)
        raise

    rows = result.get("values", [])
    if not rows:
        log.info(
            "google_sheets_read",
            ngo_slug=ngo_slug,
            sheet_id=spreadsheet_id,
            tab_name=tab_name,
            rows_affected=0,
        )
        return []

    headers = rows[0]
    data_rows = rows[1:]

    # Pad short rows so every dict has all header keys
    records = [
        dict(zip(headers, row + [""] * (len(headers) - len(row))))
        for row in data_rows
    ]

    # Log read metadata but never cell contents — cells may contain PII
    log.info(
        "google_sheets_read",
        ngo_slug=ngo_slug,
        sheet_id=spreadsheet_id,
        tab_name=tab_name,
        rows_affected=len(records),
    )
    return records


async def append_row(
    spreadsheet_id: str,
    tab_name: str,
    row_data: dict,
    credentials: Credentials,
    ngo_slug: str,
) -> int:
    """Append a row to the tab and return its 1-based row number (excl. header).

    Validates that row_data keys are a subset of the tab's defined headers.
    Extra keys are silently ignored; missing keys default to empty string.
    """
    expected_headers = TAB_HEADERS.get(tab_name, [])
    if expected_headers:
        unknown_keys = set(row_data.keys()) - set(expected_headers)
        if unknown_keys:
            log.warning(
                "google_sheets_unknown_keys",
                ngo_slug=ngo_slug,
                tab_name=tab_name,
                unknown_keys=list(unknown_keys),
            )

    # Build the row in canonical header order, defaulting missing cols to ""
    values = [row_data.get(h, "") for h in (expected_headers or list(row_data.keys()))]

    service = await get_sheets_service(credentials)
    range_name = f"'{tab_name}'!A:A"

    def _append():
        return (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [values]},
            )
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="sheets").inc()
        result = await asyncio.to_thread(_append)
    except HttpError as exc:
        _handle_sheets_error(exc, ngo_slug, "append_row", spreadsheet_id, tab_name)
        raise

    # Parse "Tab!A42:H42" to extract row number
    updated_range = result["updates"]["updatedRange"]
    row_number = _parse_row_number_from_range(updated_range)

    # Log row count but not cell values — row_data may contain PII
    log.info(
        "google_sheets_append",
        ngo_slug=ngo_slug,
        sheet_id=spreadsheet_id,
        tab_name=tab_name,
        rows_affected=1,
        new_row=row_number,
    )
    return row_number


async def update_row(
    spreadsheet_id: str,
    tab_name: str,
    row_index: int,  # 1-based, excluding header row
    row_data: dict,
    credentials: Credentials,
    ngo_slug: str,
) -> None:
    """Overwrite a specific row (1-based, header not counted).

    Row 1 means the first data row (sheet row 2 because row 1 is the header).
    """
    expected_headers = TAB_HEADERS.get(tab_name, [])
    values = [row_data.get(h, "") for h in (expected_headers or list(row_data.keys()))]

    # +1 offset converts 1-based data index to sheet row (header occupies row 1)
    sheet_row = row_index + 1
    range_name = f"'{tab_name}'!A{sheet_row}"
    service = await get_sheets_service(credentials)

    def _update():
        return (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": [values]},
            )
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="sheets").inc()
        await asyncio.to_thread(_update)
    except HttpError as exc:
        _handle_sheets_error(exc, ngo_slug, "update_row", spreadsheet_id, tab_name)
        raise

    # Log row number but not values — values may contain PII
    log.info(
        "google_sheets_update",
        ngo_slug=ngo_slug,
        sheet_id=spreadsheet_id,
        tab_name=tab_name,
        rows_affected=1,
        row_index=row_index,
    )


async def find_and_update_row(
    spreadsheet_id: str,
    tab_name: str,
    match_column: str,
    match_value: str,
    updates: dict,
    credentials: Credentials,
    ngo_slug: str,
) -> bool:
    """Find the first row where match_column == match_value and apply updates.

    Returns True if a row was found and updated, False if not found.
    Caller decides whether to append a new row or raise on not-found.
    """
    rows = await read_tab(spreadsheet_id, tab_name, credentials, ngo_slug)
    target_index = None

    for i, row in enumerate(rows, start=1):
        if row.get(match_column) == match_value:
            target_index = i
            break

    if target_index is None:
        log.info(
            "google_sheets_row_not_found",
            ngo_slug=ngo_slug,
            sheet_id=spreadsheet_id,
            tab_name=tab_name,
            match_column=match_column,
            # Deliberately not logging match_value — it could be a donor name (PII)
        )
        return False

    # Merge updates into the existing row dict before writing back
    existing_row = rows[target_index - 1]
    existing_row.update(updates)
    await update_row(
        spreadsheet_id, tab_name, target_index, existing_row, credentials, ngo_slug
    )
    return True


async def get_summary_stats(
    spreadsheet_id: str,
    tab_name: str,
    credentials: Credentials,
    ngo_slug: str,
) -> dict:
    """Return structural metadata about a tab for agent context-building.

    Agents call this before querying so they know what data is available
    without loading the entire tab (avoids unnecessary PII exposure).
    """
    service = await get_sheets_service(credentials)

    def _get_meta():
        return (
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=[f"'{tab_name}'!A1:ZZ1"],
                includeGridData=True,
                fields="sheets(properties,data.rowData.values.formattedValue)",
            )
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="sheets").inc()
        meta = await asyncio.to_thread(_get_meta)
    except HttpError as exc:
        _handle_sheets_error(exc, ngo_slug, "get_summary_stats", spreadsheet_id, tab_name)
        raise

    sheets = meta.get("sheets", [])
    if not sheets:
        return {"tab_name": tab_name, "row_count": 0, "columns": [], "last_updated": None}

    sheet_props = sheets[0].get("properties", {})
    grid_props = sheet_props.get("gridProperties", {})
    # rowCount includes header, so subtract 1 for data rows
    row_count = max(0, grid_props.get("rowCount", 1) - 1)

    # Extract column names from the header row (first row of returned data)
    row_data = sheets[0].get("data", [{}])[0].get("rowData", [])
    columns: list[str] = []
    if row_data:
        columns = [
            cell.get("formattedValue", "")
            for cell in row_data[0].get("values", [])
            if cell.get("formattedValue")
        ]

    log.info(
        "google_sheets_summary_stats",
        ngo_slug=ngo_slug,
        sheet_id=spreadsheet_id,
        tab_name=tab_name,
        row_count=row_count,
    )

    return {
        "tab_name": tab_name,
        "row_count": row_count,
        "columns": columns,
        # last_updated is not available from the Sheets API without a Drive API call;
        # agents can call drive.list_files and match the spreadsheet_id if needed
        "last_updated": None,
    }


def _parse_row_number_from_range(range_str: str) -> int:
    """Extract the first row number from a Sheets A1 range string like 'Tab!A42:H42'."""
    import re
    match = re.search(r":?[A-Z]+(\d+)", range_str)
    if not match:
        return 0
    return int(match.group(1)) - 1  # subtract header row to get 1-based data index


def _handle_sheets_error(
    exc: HttpError,
    ngo_slug: str,
    operation: str,
    spreadsheet_id: str,
    tab_name: str,
) -> None:
    """Structured error logging for Sheets API errors.

    Structured fields enable specific alerting rules: quota alerts on 429,
    permission audits on 403, and auth rotation reminders on 401.
    """
    status = exc.resp.status if exc.resp else 0
    base = dict(
        ngo_slug=ngo_slug,
        operation=operation,
        sheet_id=spreadsheet_id,
        tab_name=tab_name,
        http_status=status,
    )

    if status == 429:
        log.warning("google_sheets_quota_exceeded", **base)
    elif status == 403:
        log.error("google_sheets_permission_denied", **base)
    elif status == 404:
        log.warning("google_sheets_not_found", **base)
    elif status == 401:
        log.error("google_sheets_token_expired", **base)
    else:
        log.error("google_sheets_api_error", error=str(exc), **base)
