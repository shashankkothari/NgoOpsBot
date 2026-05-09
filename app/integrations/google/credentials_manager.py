"""Credential lifecycle management for per-NGO Google OAuth tokens.

Centralises token decryption and proactive refresh so every agent and API
route calls get_valid_credentials() and never touches crypto or token state
directly.  Keeps Google auth concerns out of business logic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import google_api_calls
from app.core.security import decrypt_field
from app.integrations.google.auth import SCOPES
from app.models.ngo import NGO

logger = get_logger(__name__)
settings = get_settings()

# Google's token endpoint — duplicated from auth.py to avoid cross-module coupling
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Refresh window: proactively refresh if the token expires within this margin
_EXPIRY_BUFFER = timedelta(minutes=5)


class GoogleAuthError(Exception):
    """NGO's Google auth is invalid — they must reconnect via /api/v1/google/connect/{ngo_slug}."""
    pass


async def get_ngo_credentials(ngo: NGO) -> Optional[Credentials]:
    """Returns ready-to-use Credentials or None if the NGO hasn't connected Google.

    Does NOT refresh — call refresh_if_needed() before making API calls.
    """
    # Nothing to build if the NGO hasn't completed the OAuth flow yet
    if not ngo.google_refresh_token:
        return None

    refresh_token = decrypt_field(ngo.google_refresh_token)

    # token=None forces a refresh on first API call — acceptable since callers
    # always invoke refresh_if_needed() before any real API work
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URL,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )


async def refresh_if_needed(
    credentials: Credentials,
    ngo: NGO,
    db: AsyncSession,
) -> Credentials:
    """Proactively refreshes the access token if expired or expiring within 5 minutes.

    Raises GoogleAuthError if the refresh_token has been revoked by the NGO or Google.
    """
    now = datetime.now(timezone.utc)

    # token=None (our initial state) counts as expired; expiry check covers renewals
    token_expired = credentials.expired or credentials.token is None
    expiring_soon = (
        credentials.expiry is not None
        and credentials.expiry.replace(tzinfo=timezone.utc) < now + _EXPIRY_BUFFER
    )

    if not (token_expired or expiring_soon):
        return credentials

    logger.info("google_token_refresh_needed", ngo_slug=ngo.slug)

    try:
        # google-auth's refresh() is synchronous — offload it to avoid blocking the loop
        await asyncio.to_thread(credentials.refresh, Request())
    except RefreshError as exc:
        # RefreshError means the token was revoked or expired — NGO must reconnect
        logger.warning(
            "google_token_refresh_failed",
            ngo_slug=ngo.slug,
            error=str(exc),
        )
        raise GoogleAuthError(
            f"Google refresh token for NGO '{ngo.slug}' is invalid or revoked. "
            "The NGO must reconnect via /api/v1/google/connect/{ngo_slug}."
        ) from exc

    google_api_calls.labels(ngo_slug=ngo.slug, service="auth").inc()
    logger.info("google_token_refreshed", ngo_slug=ngo.slug)

    # Access tokens live in-memory per request — no need to persist them.
    # The refresh_token itself never changes unless the NGO revokes and reconnects.
    return credentials


async def get_valid_credentials(ngo: NGO, db: AsyncSession) -> Credentials:
    """Convenience wrapper: decrypt, build, and refresh in one call.

    Single entry point for all agent and route code — avoids scatter of
    get_ngo_credentials / refresh_if_needed calls across the codebase.
    """
    credentials = await get_ngo_credentials(ngo)
    if credentials is None:
        raise GoogleAuthError(
            f"NGO '{ngo.slug}' has not connected a Google account. "
            "Direct them to /api/v1/google/connect/{ngo_slug}."
        )
    return await refresh_if_needed(credentials, ngo, db)
