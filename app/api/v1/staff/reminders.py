"""
Staff reminders endpoints.

GET  /api/v1/staff/reminders                — list reminders targeting this staff
POST /api/v1/staff/reminders                — create a new reminder
POST /api/v1/staff/reminders/{id}/acknowledge  — acknowledge (deactivate) a reminder
POST /api/v1/staff/reminders/{id}/snooze       — snooze a reminder
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comms.telegram_sender import send_to_group
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import get_current_staff
from app.models.ngo import NGO
from app.models.reminder import Reminder
from app.models.staff import Staff
from app.schemas.reminder import ReminderRead

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class StaffReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    scheduled_at: datetime
    repeat: str = Field(
        ...,
        pattern="^(one_time|daily|weekly|monthly)$",
    )
    assignee_type: str = Field(
        ...,
        pattern="^(all|managers|specific)$",
    )
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    agent_name: Optional[str] = Field(default=None, max_length=50)
    snooze_options_hours: list[int] = Field(default_factory=list)


class SnoozeRequest(BaseModel):
    duration_hours: int = Field(..., ge=1, le=168)  # max 1 week


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_ngo_or_403(ngo_id: uuid.UUID, db: AsyncSession) -> NGO:
    result = await db.execute(select(NGO).where(NGO.id == ngo_id, NGO.is_active.is_(True)))
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=403, detail="NGO not found or inactive")
    return ngo


# Map assignee_type vocabulary to the Reminder model's target_audience vocabulary
_AUDIENCE_MAP = {
    "all": "staff_group",
    "managers": "staff_group",  # "managers" is a subset of staff_group; filtered by role
    "specific": "specific_staff",
}


def _build_target_details(payload: StaffReminderCreate) -> dict[str, Any]:
    """Translate the API payload into Reminder.target_details JSONB."""
    if payload.assignee_type == "specific":
        return {"staff_ids": [str(sid) for sid in payload.assignee_ids]}
    if payload.assignee_type == "managers":
        return {"role_filter": "admin"}
    return {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/reminders", response_model=list[ReminderRead])
async def list_reminders(
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> list[ReminderRead]:
    """
    Return active reminders for this NGO that target the authenticated staff member.

    Targeting rules:
    - target_audience == "staff_group"  → all staff (and managers); always shown
    - target_audience == "specific_staff" and staff.id in target_details["staff_ids"]
    """
    result = await db.execute(
        select(Reminder)
        .where(
            Reminder.ngo_id == staff.ngo_id,
            Reminder.is_active.is_(True),
            or_(
                Reminder.target_audience == "staff_group",
                Reminder.target_audience == "specific_staff",
            ),
        )
        .order_by(Reminder.next_fire_at.asc().nullslast())
    )
    reminders = result.scalars().all()

    # Filter specific_staff rows client-side (simpler than a JSONB contains query
    # across DBs, and the number of reminders per NGO is small)
    staff_id_str = str(staff.id)
    visible = [
        r for r in reminders
        if r.target_audience == "staff_group"
        or staff_id_str in (r.target_details or {}).get("staff_ids", [])
    ]

    return [ReminderRead.model_validate(r) for r in visible]


@router.post("/reminders", response_model=ReminderRead, status_code=201)
async def create_reminder(
    payload: StaffReminderCreate,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> ReminderRead:
    """
    Create a new reminder for this NGO.

    Maps the staff-facing vocabulary to the internal Reminder model:
    - ``message`` and ``snooze_options_hours`` go into ``config`` JSONB
    - ``assignee_type`` maps to ``target_audience``
    - ``assignee_ids`` goes into ``target_details``
    - ``repeat`` maps to ``reminder_type`` (one_time → date_based, others → recurring)
    """
    # Determine reminder_type from repeat
    if payload.repeat == "one_time":
        reminder_type = "date_based"
        config: dict[str, Any] = {
            "message": payload.message,
            "date": payload.scheduled_at.date().isoformat(),
            "time": payload.scheduled_at.strftime("%H:%M"),
            "snooze_options_hours": payload.snooze_options_hours,
        }
    else:
        reminder_type = "recurring"
        # Build a simple cron expression from repeat
        cron_map = {
            "daily": f"0 {payload.scheduled_at.hour} * * *",
            "weekly": f"0 {payload.scheduled_at.hour} * * {payload.scheduled_at.weekday()}",
            "monthly": f"0 {payload.scheduled_at.hour} {payload.scheduled_at.day} * *",
        }
        config = {
            "message": payload.message,
            "cron": cron_map.get(payload.repeat, "0 9 * * *"),
            "snooze_options_hours": payload.snooze_options_hours,
        }

    target_audience = _AUDIENCE_MAP.get(payload.assignee_type, "staff_group")
    target_details = _build_target_details(payload)

    reminder = Reminder(
        ngo_id=staff.ngo_id,
        title=payload.title,
        reminder_type=reminder_type,
        agent_name=payload.agent_name,
        config=config,
        target_audience=target_audience,
        target_details=target_details,
        requires_approval=False,
        is_active=True,
        next_fire_at=payload.scheduled_at,
    )
    db.add(reminder)
    await db.flush()

    log.info(
        "staff_reminder_created",
        staff_id=str(staff.id),
        ngo_id=str(staff.ngo_id),
        reminder_id=str(reminder.id),
    )
    return ReminderRead.model_validate(reminder)


@router.post("/reminders/{reminder_id}/acknowledge", status_code=200)
async def acknowledge_reminder(
    reminder_id: uuid.UUID,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Acknowledge a reminder — marks it inactive and notifies the NGO group.

    Sends: "{staff.name} has acknowledged: {reminder.title}"
    """
    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.ngo_id == staff.ngo_id,
        )
    )
    reminder = result.scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.is_active = False

    ngo = await _get_ngo_or_403(staff.ngo_id, db)

    await db.flush()

    # Fire-and-forget group notification — don't let send failure abort the ack
    try:
        await send_to_group(
            ngo=ngo,
            message=f"{staff.name} has acknowledged: {reminder.title}",
        )
    except Exception as exc:
        log.warning(
            "acknowledge_reminder_notify_failed",
            reminder_id=str(reminder_id),
            error=str(exc),
        )

    log.info(
        "reminder_acknowledged",
        staff_id=str(staff.id),
        reminder_id=str(reminder_id),
    )
    return {"status": "acknowledged"}


@router.post("/reminders/{reminder_id}/snooze", status_code=200)
async def snooze_reminder(
    reminder_id: uuid.UUID,
    body: SnoozeRequest,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Snooze a reminder by ``duration_hours`` hours.

    Updates ``next_fire_at`` and notifies the NGO group:
    "{staff.name} snoozed '{reminder.title}' for {duration_hours}h"
    """
    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.ngo_id == staff.ngo_id,
        )
    )
    reminder = result.scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    now = datetime.now(timezone.utc)
    reminder.next_fire_at = now + timedelta(hours=body.duration_hours)

    ngo = await _get_ngo_or_403(staff.ngo_id, db)

    await db.flush()

    try:
        await send_to_group(
            ngo=ngo,
            message=(
                f"{staff.name} snoozed '{reminder.title}' "
                f"for {body.duration_hours}h"
            ),
        )
    except Exception as exc:
        log.warning(
            "snooze_reminder_notify_failed",
            reminder_id=str(reminder_id),
            error=str(exc),
        )

    log.info(
        "reminder_snoozed",
        staff_id=str(staff.id),
        reminder_id=str(reminder_id),
        duration_hours=body.duration_hours,
    )
    return {"status": "snoozed", "next_fire_at": reminder.next_fire_at.isoformat()}
