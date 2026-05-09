"""Admin CRUD for NGO staff members."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.ngo import NGO
from app.models.staff import Staff
from app.schemas.staff import PaginatedStaff, StaffCreate, StaffRead, StaffUpdate
from datetime import datetime, timezone

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin/ngos", tags=["admin-staff"])


async def _get_ngo_or_404(ngo_id: uuid.UUID, db: AsyncSession) -> NGO:
    result = await db.execute(select(NGO).where(NGO.id == ngo_id))
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=404, detail="NGO not found")
    return ngo


async def _get_staff_or_404(
    staff_id: uuid.UUID, ngo_id: uuid.UUID, db: AsyncSession
) -> Staff:
    result = await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.ngo_id == ngo_id)
    )
    staff = result.scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


async def _write_audit(
    db: AsyncSession,
    action: str,
    ngo_id: uuid.UUID,
    details: dict[str, Any],
    request: Request,
) -> None:
    entry = AuditLog(
        ngo_id=ngo_id,
        action=action,
        details=details,
        ip_address=request.client.host if request.client else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)


@router.post("/{ngo_id}/staff", response_model=StaffRead, status_code=201)
async def add_staff(
    ngo_id: uuid.UUID,
    payload: StaffCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StaffRead:
    await _get_ngo_or_404(ngo_id, db)

    staff = Staff(
        ngo_id=ngo_id,
        telegram_user_id=payload.telegram_user_id,
        telegram_username=payload.telegram_username,
        name=payload.name,
        role=payload.role,
        allowed_agents=payload.allowed_agents,
        phone=payload.phone,
        email=payload.email,
    )
    db.add(staff)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A staff member with this Telegram user ID already exists for this NGO",
        )

    await _write_audit(
        db,
        "staff_created",
        ngo_id,
        {"staff_id": str(staff.id), "name": staff.name, "role": staff.role},
        request,
    )
    log.info("staff_created", ngo_id=str(ngo_id), staff_id=str(staff.id), role=staff.role)
    return StaffRead.model_validate(staff)


@router.get("/{ngo_id}/staff", response_model=PaginatedStaff)
async def list_staff(
    ngo_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedStaff:
    await _get_ngo_or_404(ngo_id, db)

    query = select(Staff).where(Staff.ngo_id == ngo_id)
    if is_active is not None:
        query = query.where(Staff.is_active == is_active)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(Staff.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    members = result.scalars().all()

    return PaginatedStaff(
        items=[StaffRead.model_validate(m) for m in members],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{ngo_id}/staff/{staff_id}", response_model=StaffRead)
async def update_staff(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    payload: StaffUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StaffRead:
    staff = await _get_staff_or_404(staff_id, ngo_id, db)

    changed: dict[str, Any] = {}
    if payload.name is not None:
        staff.name = payload.name
        changed["name"] = payload.name
    if payload.role is not None:
        staff.role = payload.role
        changed["role"] = payload.role
    if payload.allowed_agents is not None:
        staff.allowed_agents = payload.allowed_agents
        changed["allowed_agents"] = payload.allowed_agents
    if payload.is_active is not None:
        staff.is_active = payload.is_active
        changed["is_active"] = payload.is_active
    if payload.phone is not None:
        staff.phone = payload.phone
        changed["phone"] = payload.phone
    if payload.email is not None:
        staff.email = payload.email
        changed["email"] = payload.email
    if payload.telegram_username is not None:
        staff.telegram_username = payload.telegram_username
        changed["telegram_username"] = payload.telegram_username

    await _write_audit(
        db, "staff_updated", ngo_id,
        {"staff_id": str(staff_id), **changed},
        request,
    )
    log.info("staff_updated", ngo_id=str(ngo_id), staff_id=str(staff_id))
    return StaffRead.model_validate(staff)


@router.delete("/{ngo_id}/staff/{staff_id}", status_code=204)
async def deactivate_staff(
    ngo_id: uuid.UUID,
    staff_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete: sets is_active=False. Telegram user ID is preserved for audit history."""
    staff = await _get_staff_or_404(staff_id, ngo_id, db)
    staff.is_active = False
    await _write_audit(
        db, "staff_deactivated", ngo_id,
        {"staff_id": str(staff_id), "name": staff.name},
        request,
    )
    log.info("staff_deactivated", ngo_id=str(ngo_id), staff_id=str(staff_id))
