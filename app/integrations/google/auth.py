"""Google OAuth 2.0 helpers for NGO account connection.

Scopes are chosen by least-privilege: drive.file restricts Drive access to only
files the app itself creates, preventing read access to the NGO's entire Drive.
"""

from __future__ import annotations

import secrets

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_field

log = get_logger(__name__)

# Scopes are additive — we request only what each integration requires.
# drive.file: files created by this app only (not the NGO's entire Drive).
# drive.readonly: read arbitrary Drive files so agents can reference documents.
# spreadsheets: full read/write access to Sheets (needed for Master Tracker).
# gmail.readonly: read emails so agents can reference donor/grant correspondence.
# gmail.compose: create drafts (NOT send) — staff must review before sending.
# calendar.readonly: read events so agents can check deadlines and schedules.
# calendar.events: create/update events (reminders, grant deadlines, etc.).
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# Google's token revocation endpoint
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_flow(redirect_uri: str | None = None) -> Flow:
    """Build an OAuth Flow from app settings; redirect_uri overridable for tests."""
    cfg = get_settings()
    client_config = {
        "web": {
            "client_id": cfg.GOOGLE_CLIENT_ID,
            "client_secret": cfg.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": _TOKEN_URL,
            "redirect_uris": [redirect_uri or cfg.GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri or cfg.GOOGLE_REDIRECT_URI,
    )


def get_authorization_url(ngo_slug: str, state: str) -> str:
    """Build the Google OAuth consent URL with CSRF state token.

    state embeds ngo_slug so the callback can route back to the right tenant.
    access_type=offline forces a refresh_token; prompt=consent re-issues it
    even if the user has previously consented (avoids stale grant edge cases).
    """
    flow = _get_flow()
    # Combine slug + caller-supplied CSRF token so callback validates both
    combined_state = f"{ngo_slug}:{state}"
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=combined_state,
        include_granted_scopes="false",  # fresh grant each time, not incremental
    )
    log.info("google_oauth_url_generated", ngo_slug=ngo_slug)
    return auth_url


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange the authorization code for access + refresh tokens.

    Returns raw token dict — the caller encrypts and persists the refresh_token.
    Keeping encryption out of here makes this function unit-testable in isolation.
    """
    cfg = get_settings()
    # httpx is async-native; avoids blocking the event loop for the token exchange
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": cfg.GOOGLE_CLIENT_ID,
                "client_secret": cfg.GOOGLE_CLIENT_SECRET,
                "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        tokens = resp.json()

    # Log the event but never the token values
    log.info(
        "google_tokens_exchanged",
        scopes=tokens.get("scope", ""),
        has_refresh_token=bool(tokens.get("refresh_token")),
    )
    return tokens


async def get_credentials(encrypted_refresh_token: str) -> Credentials:
    """Decrypt the stored refresh token and build a Credentials object.

    Does NOT proactively refresh — the API call itself triggers refresh via
    google-auth's request() interceptor.  Callers must catch RefreshError
    and prompt the NGO to reconnect.
    """
    cfg = get_settings()
    refresh_token = decrypt_field(encrypted_refresh_token)
    creds = Credentials(
        token=None,  # no access token yet — first API call will fetch one
        refresh_token=refresh_token,
        token_uri=_TOKEN_URL,
        client_id=cfg.GOOGLE_CLIENT_ID,
        client_secret=cfg.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return creds


async def revoke_tokens(encrypted_refresh_token: str) -> None:
    """Revoke the NGO's refresh token on Google's servers.

    Called on disconnect — required for GDPR compliance so the NGO can be
    confident the app can no longer act on their behalf after disconnection.
    """
    refresh_token = decrypt_field(encrypted_refresh_token)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _REVOKE_URL,
            params={"token": refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # 400 means token already expired/revoked — still a clean state, not an error
        if resp.status_code not in (200, 400):
            resp.raise_for_status()

    # Log the event; never log the token itself
    log.info("google_tokens_revoked")


def build_oauth_callback_url(ngo_slug: str) -> str:
    """Return the full redirect_uri for this NGO's OAuth callback.

    Useful when the redirect_uri must embed per-tenant routing, though currently
    we use a single shared callback and route by state parameter.
    """
    cfg = get_settings()
    # The redirect_uri must exactly match what's registered in Google Cloud Console
    return cfg.GOOGLE_REDIRECT_URI
