"""
Staff profile endpoint.

GET /api/v1/staff/me  — returns the authenticated staff member's profile.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import get_current_staff
from app.models.ngo import NGO
from app.models.staff import Staff
from app.schemas.staff import StaffProfile

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


@router.get("/me", response_model=StaffProfile)
async def get_me(
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> StaffProfile:
    """Return the JWT-authenticated staff member's profile with NGO context."""
    result = await db.execute(select(NGO).where(NGO.id == staff.ngo_id))
    ngo = result.scalar_one_or_none()

    if ngo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="NGO not found")

    return StaffProfile(
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
