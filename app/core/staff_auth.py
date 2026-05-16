"""
Staff JWT authentication utilities.

Flow:
  1. Client sends a Google ID token (from NextAuth / Google Sign-In).
  2. ``verify_google_token`` validates it against Google's public keys.
  3. ``get_staff_from_google`` looks up the Staff row by email — 401 if not found.
  4. ``create_staff_jwt`` mints a 24-hour HS256 JWT with staff claims.
  5. ``get_current_staff`` is the FastAPI dependency that verifies the JWT on every
     protected staff endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import asyncio
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.staff import Staff

log = get_logger(__name__)

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Google ID token verification
# ---------------------------------------------------------------------------

async def verify_google_token(id_token: str) -> dict:
    """
    Verify a Google ID token and return the decoded claims.

    Uses google-auth's ``id_token.verify_oauth2_token`` which validates
    the signature against Google's public certs, checks ``aud`` matches
    our GOOGLE_CLIENT_ID, and enforces ``exp``.

    Runs the blocking I/O (cert fetch) in a thread pool so the event
    loop is not stalled.

    Raises HTTPException 401 on any verification failure.
    """
    import google.auth.transport.requests
    import google.oauth2.id_token

    settings = get_settings()

    def _verify() -> dict:
        request = google.auth.transport.requests.Request()
        return google.oauth2.id_token.verify_oauth2_token(
            id_token,
            request,
            audience=settings.GOOGLE_CLIENT_ID or None,
        )

    try:
        claims: dict = await asyncio.to_thread(_verify)
    except Exception as exc:
        log.warning("google_token_verification_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid Google ID token") from exc

    return claims


# ---------------------------------------------------------------------------
# Staff lookup
# ---------------------------------------------------------------------------

async def get_staff_from_google(
    id_token: str,
    db: AsyncSession,
    ngo_slug: str | None = None,
) -> "Staff":
    """
    Verify the Google token and find the matching Staff row by email.

    If ngo_slug is provided, the lookup is scoped to that NGO — staff from
    other NGOs with the same email are rejected. This prevents a staff member
    at one NGO from accidentally (or maliciously) signing into another.

    Raises:
      HTTPException 401 — token invalid or email not found in the staff table.
    """
    claims = await verify_google_token(id_token)

    email: str | None = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Google token contains no email claim")

    from app.models.ngo import NGO
    from app.models.staff import Staff

    query = (
        select(Staff)
        .where(Staff.email == email, Staff.is_active.is_(True))
    )

    if ngo_slug:
        query = (
            select(Staff)
            .join(NGO, NGO.id == Staff.ngo_id)
            .where(
                Staff.email == email,
                Staff.is_active.is_(True),
                NGO.slug == ngo_slug,
                NGO.is_active.is_(True),
            )
        )

    result = await db.execute(query)
    staff = result.scalars().first()
    if staff is None:
        log.warning("staff_google_login_not_found", email=email, ngo_slug=ngo_slug)
        raise HTTPException(
            status_code=401,
            detail="No active staff account found for this Google email"
            + (f" in NGO '{ngo_slug}'" if ngo_slug else ""),
        )

    log.info(
        "staff_google_login_ok",
        staff_id=str(staff.id),
        ngo_id=str(staff.ngo_id),
    )
    return staff


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------

def create_staff_jwt(staff: "Staff", ngo: "NGO") -> str:
    """
    Mint a signed 24-hour HS256 JWT for the staff member.

    Payload:
      sub         — staff.id (str)
      ngo_id      — ngo.id (str)
      ngo_slug    — ngo.slug
      role        — staff.role ("admin" | "staff")
      allowed_agents — list[str]
      exp         — expiry (24 h from now)
      iat         — issued-at
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=_TOKEN_EXPIRE_HOURS)

    payload: dict = {
        "sub": str(staff.id),
        "ngo_id": str(ngo.id),
        "ngo_slug": ngo.slug,
        "role": staff.role,
        "allowed_agents": staff.allowed_agents or [],
        "exp": expire,
        "iat": now,
    }

    token: str = jwt.encode(payload, settings.STAFF_JWT_SECRET, algorithm=_ALGORITHM)
    return token


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> "Staff":
    """
    FastAPI dependency — decode the Bearer JWT and return the Staff row.

    Raises HTTPException 401 if the token is missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    settings = get_settings()
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.STAFF_JWT_SECRET,
            algorithms=[_ALGORITHM],
        )
    except InvalidTokenError as exc:
        log.warning("staff_jwt_decode_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    staff_id_str: str | None = payload.get("sub")
    if not staff_id_str:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    try:
        staff_id = uuid.UUID(staff_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token subject is not a valid UUID") from exc

    from app.models.staff import Staff

    result = await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.is_active.is_(True))
    )
    staff = result.scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=401, detail="Staff member not found or inactive")

    return staff
