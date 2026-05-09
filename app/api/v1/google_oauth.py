"""Google OAuth 2.0 flow endpoints for per-NGO account connection.

Handles the full connect → callback → status → disconnect lifecycle.
State tokens live in Redis (not DB) because they are ephemeral, must expire
automatically, and must be consumed exactly once — all properties Redis TTL
and DEL give us for free.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import encrypt_field
from app.integrations.google.auth import (
    exchange_code_for_tokens,
    get_authorization_url,
    revoke_tokens,
)
from app.integrations.google.credentials_manager import get_ngo_credentials
from app.integrations.google.drive import setup_ngo_drive
from app.models.audit import AuditLog
from app.models.ngo import NGO

router = APIRouter(tags=["google-oauth"])
logger = get_logger(__name__)

# Redis key template; TTL matches Google's recommended OAuth state lifetime
_STATE_KEY = "google_oauth_state:{ngo_slug}"
_STATE_TTL_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_active_ngo_or_404(ngo_slug: str, db: AsyncSession) -> NGO:
    """Fetch an active NGO by slug or raise a descriptive 404."""
    result = await db.execute(
        select(NGO).where(NGO.slug == ngo_slug, NGO.is_active == True)  # noqa: E712
    )
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(
            status_code=404,
            detail=f"NGO '{ngo_slug}' not found or inactive.",
        )
    return ngo


async def _write_audit(
    db: AsyncSession,
    action: str,
    ngo: NGO,
    details: dict,
) -> None:
    """Append an audit row within the caller's open transaction."""
    entry = AuditLog(
        ngo_id=ngo.id,
        action=action,
        details=details,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)


async def _setup_drive_async(ngo_id, ngo_slug: str, encrypted_refresh_token: str) -> None:
    """Background task: build Drive folder structure after OAuth completes.

    Runs outside the request's DB session, so it opens its own session.
    Isolated so a Drive API failure never rolls back the token save.
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(NGO).where(NGO.id == ngo_id))
            ngo = result.scalar_one_or_none()
            if ngo is None:
                logger.error("drive_setup_ngo_missing", ngo_id=str(ngo_id))
                return

            credentials = await get_ngo_credentials(ngo)
            if credentials is None:
                logger.error("drive_setup_no_credentials", ngo_slug=ngo_slug)
                return

            # Credentials need at least one refresh before API calls work
            from google.auth.transport.requests import Request
            import asyncio
            await asyncio.to_thread(credentials.refresh, Request())

            folder_id, sheet_id = await setup_ngo_drive(ngo, credentials)

            await db.execute(
                update(NGO)
                .where(NGO.id == ngo_id)
                .values(
                    google_drive_folder_id=folder_id,
                    google_master_sheet_id=sheet_id,
                )
            )
            await db.commit()

            logger.info(
                "google_drive_setup_complete",
                ngo_slug=ngo_slug,
                folder_id=folder_id,
                sheet_id=sheet_id,
            )
        except Exception as exc:
            # Don't let a Drive failure surface to the user — OAuth is already saved
            logger.error("google_drive_setup_failed", ngo_slug=ngo_slug, error=str(exc))
            await db.rollback()


# ---------------------------------------------------------------------------
# GET /connect/{ngo_slug}
# ---------------------------------------------------------------------------

@router.get("/connect/{ngo_slug}", response_class=RedirectResponse)
async def connect_google(
    ngo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Initiate the Google OAuth consent flow for an NGO.

    Stores a CSRF state token in Redis with a 10-minute TTL so the callback
    can verify the round-trip and prevent cross-site request forgery.
    """
    ngo = await _get_active_ngo_or_404(ngo_slug, db)

    # CSRF token binds this flow to this browser session via Redis
    state_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.set(
        _STATE_KEY.format(ngo_slug=ngo_slug),
        state_token,
        ex=_STATE_TTL_SECONDS,
    )

    # state param carries both ngo_slug and the CSRF token for callback routing
    state = f"{ngo_slug}:{state_token}"
    auth_url = get_authorization_url(ngo_slug, state_token)

    logger.info("google_oauth_initiated", ngo_slug=ngo_slug)
    return RedirectResponse(url=auth_url, status_code=302)


# ---------------------------------------------------------------------------
# GET /callback
# ---------------------------------------------------------------------------

@router.get("/callback")
async def google_callback(
    background_tasks: BackgroundTasks,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="CSRF state: {ngo_slug}:{state_token}"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Handle Google's OAuth callback, exchange the code, and persist the token.

    Drive setup runs as a background task so the user gets an immediate response
    even though folder creation and sheet setup can take several seconds.
    """
    # State encodes ngo_slug:state_token — split on first colon only
    parts = state.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid OAuth state parameter.")

    ngo_slug, state_token = parts

    # One-time-use validation: delete atomically after reading
    redis = await get_redis()
    stored_token = await redis.getdel(_STATE_KEY.format(ngo_slug=ngo_slug))

    if stored_token is None:
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired or already used. Please restart the connection flow.",
        )
    if stored_token != state_token:
        # Mismatched token indicates CSRF attempt or replay — fail loudly
        logger.warning("google_oauth_state_mismatch", ngo_slug=ngo_slug)
        raise HTTPException(status_code=400, detail="OAuth state mismatch. Connection rejected.")

    ngo = await _get_active_ngo_or_404(ngo_slug, db)

    tokens = await exchange_code_for_tokens(code)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Google only issues a refresh_token when prompt=consent — missing means
        # the NGO had an existing grant without revoke; the flow in auth.py forces
        # prompt=consent, so this should not happen in normal operation
        raise HTTPException(
            status_code=502,
            detail=(
                "Google did not return a refresh token. "
                "Please revoke app access in your Google account and try again."
            ),
        )

    # Encrypt before persistence — plaintext tokens never touch the DB
    ngo.google_refresh_token = encrypt_field(refresh_token)
    await _write_audit(db, "google_connected", ngo, {"ngo_slug": ngo_slug})
    # Flush so the token is committed before the background task reads it
    await db.flush()

    # Drive setup is slow (multiple API calls) — don't block the OAuth response
    background_tasks.add_task(
        _setup_drive_async,
        ngo.id,
        ngo_slug,
        ngo.google_refresh_token,
    )

    logger.info("google_oauth_complete", ngo_slug=ngo_slug)

    settings = get_settings()
    html = f"""
    <!DOCTYPE html>
    <html>
      <head><title>Google Connected — NGO OpsBot</title></head>
      <body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto; text-align: center;">
        <h2>Google connected successfully!</h2>
        <p>
          <strong>{ngo.name}</strong> is now linked to Google.<br>
          Your Drive folder and Master Tracker are being set up in the background —
          this usually takes under a minute.
        </p>
        <p>You can close this window.</p>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)


# ---------------------------------------------------------------------------
# GET /status/{ngo_slug}
# ---------------------------------------------------------------------------

@router.get("/status/{ngo_slug}")
async def google_status(
    ngo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return the NGO's Google connection status and resource URLs."""
    ngo = await _get_active_ngo_or_404(ngo_slug, db)

    connected = ngo.google_refresh_token is not None

    drive_url = (
        f"https://drive.google.com/drive/folders/{ngo.google_drive_folder_id}"
        if ngo.google_drive_folder_id
        else None
    )
    sheet_url = (
        f"https://docs.google.com/spreadsheets/d/{ngo.google_master_sheet_id}"
        if ngo.google_master_sheet_id
        else None
    )

    return JSONResponse(
        content={
            "connected": connected,
            "drive_folder_id": ngo.google_drive_folder_id,
            "master_sheet_id": ngo.google_master_sheet_id,
            "drive_url": drive_url,
            "sheet_url": sheet_url,
        }
    )


# ---------------------------------------------------------------------------
# POST /disconnect/{ngo_slug}
# ---------------------------------------------------------------------------

@router.post("/disconnect/{ngo_slug}")
async def disconnect_google(
    ngo_slug: str,
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Revoke the NGO's Google token and clear all Google fields.

    Requires the admin API key — NGO-level actors must not be able to
    disconnect other tenants or manipulate their own token lifecycle directly.
    """
    settings = get_settings()
    # Constant-time comparison prevents timing-based key enumeration.
    valid = bool(x_admin_api_key) and hmac.compare_digest(
        x_admin_api_key.encode(), settings.ADMIN_API_KEY.encode()
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key.")

    ngo = await _get_active_ngo_or_404(ngo_slug, db)

    if ngo.google_refresh_token:
        try:
            await revoke_tokens(ngo.google_refresh_token)
        except Exception as exc:
            # Token may already be revoked (NGO removed app from Google account)
            # Log it but continue — we still want to clear our local state
            logger.warning(
                "google_revoke_failed",
                ngo_slug=ngo_slug,
                error=str(exc),
            )

    # Clear all Google fields — NGO is fully disconnected from our perspective
    ngo.google_refresh_token = None
    ngo.google_drive_folder_id = None
    ngo.google_master_sheet_id = None

    await _write_audit(db, "google_disconnected", ngo, {"ngo_slug": ngo_slug})

    logger.info("google_disconnected", ngo_slug=ngo_slug)
    return JSONResponse(content={"disconnected": True})
