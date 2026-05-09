"""Google Drive operations for NGO file and folder management.

google-api-python-client is synchronous, so every API call is wrapped in
asyncio.to_thread() to prevent blocking the event loop under load.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2.credentials import Credentials

from app.core.logging import get_logger
from app.core.metrics import google_api_calls
from app.models.ngo import NGO

log = get_logger(__name__)

# Folder MIME type is a Drive-specific constant, not a real file format
_FOLDER_MIME = "application/vnd.google-apps.folder"
_SHEET_MIME = "application/vnd.google-apps.spreadsheet"


async def get_drive_service(credentials: Credentials):
    """Build a Drive API v3 service object, wrapped for async use.

    The service object is not thread-safe for concurrent calls, so callers
    should create one per operation (cheap — no network call at build time).
    """
    return await asyncio.to_thread(
        build, "drive", "v3", credentials=credentials, cache_discovery=False
    )


async def create_folder(name: str, parent_id: Optional[str], service) -> str:
    """Create a Drive folder and return its ID.

    Does NOT check for duplicates — use get_or_create_folder for idempotency.
    """
    metadata = {
        "name": name,
        "mimeType": _FOLDER_MIME,
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    def _create():
        return (
            service.files()
            .create(body=metadata, fields="id")
            .execute()
        )

    result = await asyncio.to_thread(_create)
    return result["id"]


async def get_or_create_folder(
    name: str, parent_id: Optional[str], service
) -> str:
    """Return existing folder ID or create one — idempotent across reconnects.

    Searching by name+parent before creating prevents duplicate folder sprawl
    if setup_ngo_drive() is called multiple times (e.g., OAuth reconnect).
    """
    # Build query to find exact name match within parent scope
    parent_clause = f"'{parent_id}' in parents" if parent_id else "'root' in parents"
    query = (
        f"name = '{name}' and mimeType = '{_FOLDER_MIME}' "
        f"and {parent_clause} and trashed = false"
    )

    def _list():
        return (
            service.files()
            .list(q=query, fields="files(id, name)", pageSize=1)
            .execute()
        )

    result = await asyncio.to_thread(_list)
    files = result.get("files", [])

    if files:
        # Folder already exists — return its ID without creating a duplicate
        return files[0]["id"]

    return await create_folder(name, parent_id, service)


async def setup_ngo_drive(ngo: NGO, credentials: Credentials) -> tuple[str, str]:
    """Create the NGO's Drive folder structure and Master Tracker spreadsheet.

    Returns (folder_id, sheet_id).  Idempotent — safe to call on reconnect
    because get_or_create_folder checks before creating.

    Folder layout separates agent namespaces so each agent has a clean home
    for its reports without polluting a shared root:
        NGO OpsBot - {name}/
          ├── Master Tracker  (Google Sheet)
          ├── Fundraising/
          ├── Finance/
          ├── HR/
          └── Compliance/
    """
    service = await get_drive_service(credentials)
    root_name = f"NGO OpsBot - {ngo.name}"

    # Root folder lives in the NGO's My Drive — no parent means Drive root
    google_api_calls.labels(ngo_slug=ngo.slug, service="drive").inc()
    root_id = await get_or_create_folder(root_name, None, service)
    log.info("google_drive_root_folder", ngo_slug=ngo.slug, folder_id=root_id)

    # Subfolders give each agent a dedicated namespace for its report files
    subfolders = ["Fundraising", "Finance", "HR", "Compliance"]
    for subfolder_name in subfolders:
        google_api_calls.labels(ngo_slug=ngo.slug, service="drive").inc()
        await get_or_create_folder(subfolder_name, root_id, service)
        log.info("google_drive_subfolder", ngo_slug=ngo.slug, name=subfolder_name)

    # Master Tracker lives in the root alongside the subfolders
    from app.integrations.google.sheets import create_master_tracker
    sheet_id = await create_master_tracker(root_id, credentials, ngo.name)

    log.info(
        "google_drive_setup_complete",
        ngo_slug=ngo.slug,
        folder_id=root_id,
        sheet_id=sheet_id,
    )
    return root_id, sheet_id


async def upload_file(
    name: str,
    content: bytes,
    mime_type: str,
    folder_id: str,
    credentials: Credentials,
    ngo_slug: str,
) -> str:
    """Upload bytes to NGO's Drive folder and return the file_id.

    Uses MediaInMemoryUpload to avoid writing temp files to disk — keeps
    sensitive NGO data in process memory only.
    """
    service = await get_drive_service(credentials)
    metadata = {"name": name, "parents": [folder_id]}
    media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=False)

    def _upload():
        return (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="drive").inc()
        result = await asyncio.to_thread(_upload)
    except HttpError as exc:
        _handle_drive_error(exc, ngo_slug, operation="upload_file", file_name=name)
        raise

    file_id = result["id"]
    log.info("google_drive_file_uploaded", ngo_slug=ngo_slug, file_id=file_id, name=name)
    return file_id


async def list_files(
    folder_id: str,
    credentials: Credentials,
    ngo_slug: str,
) -> list[dict]:
    """List files in a Drive folder with essential metadata fields.

    Returns dicts with id, name, mimeType, modifiedTime.
    """
    service = await get_drive_service(credentials)
    query = f"'{folder_id}' in parents and trashed = false"

    def _list():
        return (
            service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="name",
            )
            .execute()
        )

    try:
        google_api_calls.labels(ngo_slug=ngo_slug, service="drive").inc()
        result = await asyncio.to_thread(_list)
    except HttpError as exc:
        _handle_drive_error(exc, ngo_slug, operation="list_files", folder_id=folder_id)
        raise

    files = result.get("files", [])
    log.info(
        "google_drive_files_listed",
        ngo_slug=ngo_slug,
        folder_id=folder_id,
        count=len(files),
    )
    return files


def _handle_drive_error(
    exc: HttpError,
    ngo_slug: str,
    operation: str,
    **context,
) -> None:
    """Structured logging for Drive API errors by status code.

    Logs are structured so alerting rules can target specific error types
    (quota alerts on 429, permission audits on 403, auth rotation on 401).
    """
    status = exc.resp.status if exc.resp else 0
    base = dict(ngo_slug=ngo_slug, operation=operation, http_status=status, **context)

    if status == 429:
        log.warning("google_drive_quota_exceeded", **base)
    elif status == 403:
        log.error("google_drive_permission_denied", **base)
    elif status == 404:
        log.warning("google_drive_not_found", **base)
    elif status == 401:
        log.error("google_drive_token_expired", **base)
    else:
        log.error("google_drive_api_error", error=str(exc), **base)
