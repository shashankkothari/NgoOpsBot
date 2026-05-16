"""
Staff authentication — Google ID token exchange for a platform JWT.

POST /api/v1/staff/auth/google
  Body: {id_token: str}
  Returns: {access_token: str, staff: StaffProfile}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import create_staff_jwt, get_staff_from_google
from app.models.ngo import NGO
from app.schemas.staff import StaffProfile

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff/auth", tags=["staff"])


class GoogleTokenRequest(BaseModel):
    id_token: str
    ngo_slug: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    staff: StaffProfile


@router.post("/google", response_model=AuthResponse)
async def google_login(
    payload: GoogleTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """
    Exchange a Google ID token for a platform JWT.

    The Google token is verified against Google's public keys. The staff
    member's email must exist in the staff table for any active NGO.
    """
    staff = await get_staff_from_google(payload.id_token, db, ngo_slug=payload.ngo_slug)

    # Fetch the NGO so we can embed its slug/name in the JWT and response
    result = await db.execute(select(NGO).where(NGO.id == staff.ngo_id))
    ngo = result.scalar_one_or_none()
    if ngo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="NGO for this staff member not found")

    access_token = create_staff_jwt(staff, ngo)

    staff_profile = StaffProfile(
        id=staff.id,
        name=staff.name,
        telegram_username=staff.telegram_username,
        role=staff.role,
        ngo_id=ngo.id,
        ngo_name=ngo.name,
        ngo_slug=ngo.slug,
        allowed_agents=staff.allowed_agents or [],
        email=staff.email,
    )

    log.info(
        "staff_auth_google_success",
        staff_id=str(staff.id),
        ngo_slug=ngo.slug,
    )
    return AuthResponse(access_token=access_token, staff=staff_profile)
