"""Admin CRUD and management endpoints for NGO reminders.

All routes sit under /api/v1/admin/ngos/{ngo_id}/reminders and are protected
by NGOAuthMiddleware (X-Admin-API-Key header).

Reminder lifecycle:
  - POST /          → create; if recurring, registers an APScheduler CronTrigger job
  - GET  /          → paginated list with scheduling metadata
  - PATCH/{id}      → update; swaps the APScheduler job if the cron expression changed
  - DELETE/{id}     → soft-delete (is_active=False) + remove APScheduler job
  - GET  /logs      → paginated ReminderLog (filterable by status and date range)
  - POST /{id}/fire-now → immediate ad-hoc fire for admin testing
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.ngo import NGO
from app.models.reminder import Reminder, ReminderLog
from app.schemas.reminder import ReminderCreate, ReminderLogRead, ReminderRead

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/ngos/{ngo_id}/reminders",
    tags=["admin-reminders"],
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _get_ngo_or_404(ngo_id: uuid.UUID, db: AsyncSession) -> NGO:
    """Load the NGO row; raise 404 if it doesn't exist."""
    result = await db.execute(select(NGO).where(NGO.id == ngo_id))
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=404, detail=f"NGO {ngo_id} not found")
    return ngo


async def _get_reminder_or_404(
    reminder_id: uuid.UUID,
    ngo_id: uuid.UUID,
    db: AsyncSession,
) -> Reminder:
    """Load the Reminder scoped to the NGO; raise 404 if missing."""
    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.ngo_id == ngo_id,
        )
    )
    reminder = result.scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status_code=404, detail=f"Reminder {reminder_id} not found")
    return reminder


def _initial_next_fire_at(reminder: Reminder) -> Optional[datetime]:
    """Compute next_fire_at at creation time before the first firing."""
    from app.scheduler.reminder_types import _calculate_next_fire_at

    config = reminder.config or {}

    if reminder.reminder_type == "date_based":
        # Parse the one-shot fire time directly from config.
        fire_at_str = config.get("fire_at")
        if fire_at_str:
            try:
                dt = datetime.fromisoformat(fire_at_str)
                # Ensure UTC-aware so DB column (timezone=True) is happy.
                return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None

    # For all other types, reuse the same logic the poller uses after firing.
    # For recurring, the trigger computes the actual next time; for inactivity/threshold
    # it schedules the first check relative to now.
    return _calculate_next_fire_at(reminder)


# ---------------------------------------------------------------------------
# POST / — create reminder
# ---------------------------------------------------------------------------

@router.post("/", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    ngo_id: uuid.UUID,
    payload: ReminderCreate,
    db: AsyncSession = Depends(get_db),
) -> ReminderRead:
    """Create a new reminder for the NGO; schedule a cron job if recurring."""
    await _get_ngo_or_404(ngo_id, db)

    reminder = Reminder(
        ngo_id=ngo_id,
        title=payload.title,
        reminder_type=payload.reminder_type,
        agent_name=payload.agent_name,
        config=payload.config,
        target_audience=payload.target_audience,
        target_details=payload.target_details,
        requires_approval=payload.requires_approval,
        is_active=True,
    )

    db.add(reminder)
    # Flush to get the auto-generated UUID before computing next_fire_at.
    await db.flush()

    reminder.next_fire_at = _initial_next_fire_at(reminder)
    await db.commit()
    await db.refresh(reminder)

    # Recurring reminders get a dedicated APScheduler job for sub-15-min precision.
    if payload.reminder_type == "recurring":
        cron_expr = payload.config.get("cron", "")
        tz_str = payload.config.get("timezone", "UTC")
        if cron_expr:
            try:
                from app.scheduler.engine import add_reminder_job
                await add_reminder_job(str(reminder.id), cron_expr, tz_str)
            except RuntimeError:
                # Scheduler not started yet (e.g. test env); log and continue.
                logger.warning(
                    "scheduler_not_running_skip_job",
                    reminder_id=str(reminder.id),
                )

    logger.info(
        "reminder_created",
        reminder_id=str(reminder.id),
        ngo_id=str(ngo_id),
        reminder_type=payload.reminder_type,
    )
    return ReminderRead.model_validate(reminder)


# ---------------------------------------------------------------------------
# GET / — list reminders
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ReminderRead])
async def list_reminders(
    ngo_id: uuid.UUID,
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    reminder_type: Optional[str] = Query(default=None, description="Filter by type"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ReminderRead]:
    """List reminders for the NGO with optional type/status filters."""
    await _get_ngo_or_404(ngo_id, db)

    stmt = select(Reminder).where(Reminder.ngo_id == ngo_id)
    if is_active is not None:
        stmt = stmt.where(Reminder.is_active.is_(is_active))
    if reminder_type is not None:
        stmt = stmt.where(Reminder.reminder_type == reminder_type)

    stmt = stmt.order_by(Reminder.next_fire_at.asc().nulls_last()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    reminders = result.scalars().all()
    return [ReminderRead.model_validate(r) for r in reminders]


# ---------------------------------------------------------------------------
# PATCH /{reminder_id} — update reminder
# ---------------------------------------------------------------------------

@router.patch("/{reminder_id}", response_model=ReminderRead)
async def update_reminder(
    ngo_id: uuid.UUID,
    reminder_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> ReminderRead:
    """Partial update; rebuilds the APScheduler job if the cron expression changes."""
    reminder = await _get_reminder_or_404(reminder_id, ngo_id, db)

    old_cron = (reminder.config or {}).get("cron")
    old_type = reminder.reminder_type

    allowed_fields = {
        "title", "config", "target_audience", "target_details",
        "requires_approval", "is_active", "agent_name",
    }
    for field, value in payload.items():
        if field in allowed_fields:
            setattr(reminder, field, value)

    # Recompute next_fire_at when scheduling config changes.
    if "config" in payload or "reminder_type" in payload:
        reminder.next_fire_at = _initial_next_fire_at(reminder)

    await db.commit()
    await db.refresh(reminder)

    # Sync APScheduler job when cron changes or type becomes/stops being recurring.
    new_cron = (reminder.config or {}).get("cron")
    new_type = reminder.reminder_type

    try:
        from app.scheduler.engine import add_reminder_job, remove_reminder_job

        if old_type == "recurring" and new_type != "recurring":
            # Reminder is no longer recurring — remove its dedicated job.
            await remove_reminder_job(str(reminder_id))

        elif new_type == "recurring":
            tz_str = (reminder.config or {}).get("timezone", "UTC")
            if new_cron and new_cron != old_cron:
                # Cron expression changed — replace_existing=True in add_reminder_job handles this.
                await add_reminder_job(str(reminder_id), new_cron, tz_str)
            elif new_cron and old_type != "recurring":
                # Just became recurring for the first time.
                await add_reminder_job(str(reminder_id), new_cron, tz_str)

    except RuntimeError:
        logger.warning("scheduler_not_running_skip_job_update", reminder_id=str(reminder_id))

    logger.info("reminder_updated", reminder_id=str(reminder_id), ngo_id=str(ngo_id))
    return ReminderRead.model_validate(reminder)


# ---------------------------------------------------------------------------
# DELETE /{reminder_id} — soft-delete
# ---------------------------------------------------------------------------

@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    ngo_id: uuid.UUID,
    reminder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete by setting is_active=False and removing any APScheduler job."""
    reminder = await _get_reminder_or_404(reminder_id, ngo_id, db)

    reminder.is_active = False
    await db.commit()

    # Remove the dedicated cron job if one was registered for this reminder.
    try:
        from app.scheduler.engine import remove_reminder_job
        await remove_reminder_job(str(reminder_id))
    except RuntimeError:
        logger.warning("scheduler_not_running_skip_job_remove", reminder_id=str(reminder_id))

    logger.info("reminder_deleted", reminder_id=str(reminder_id), ngo_id=str(ngo_id))


# ---------------------------------------------------------------------------
# GET /logs — paginated ReminderLog
# ---------------------------------------------------------------------------

@router.get("/logs", response_model=list[ReminderLogRead])
async def list_reminder_logs(
    ngo_id: uuid.UUID,
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="One of: sent, pending_approval, approved, rejected, failed",
    ),
    from_date: Optional[datetime] = Query(default=None, description="ISO 8601 lower bound for fired_at"),
    to_date: Optional[datetime] = Query(default=None, description="ISO 8601 upper bound for fired_at"),
    reminder_id: Optional[uuid.UUID] = Query(default=None, description="Filter to a single reminder"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ReminderLogRead]:
    """Paginated reminder audit log for the NGO."""
    await _get_ngo_or_404(ngo_id, db)

    stmt = select(ReminderLog).where(ReminderLog.ngo_id == ngo_id)

    if status_filter is not None:
        stmt = stmt.where(ReminderLog.status == status_filter)
    if from_date is not None:
        # Normalise to UTC-aware so comparison with timezone=True column works.
        if from_date.tzinfo is None:
            from_date = from_date.replace(tzinfo=timezone.utc)
        stmt = stmt.where(ReminderLog.fired_at >= from_date)
    if to_date is not None:
        if to_date.tzinfo is None:
            to_date = to_date.replace(tzinfo=timezone.utc)
        stmt = stmt.where(ReminderLog.fired_at <= to_date)
    if reminder_id is not None:
        stmt = stmt.where(ReminderLog.reminder_id == reminder_id)

    stmt = stmt.order_by(ReminderLog.fired_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [ReminderLogRead.model_validate(log) for log in logs]


# ---------------------------------------------------------------------------
# POST /{reminder_id}/fire-now — ad-hoc test fire
# ---------------------------------------------------------------------------

@router.post("/{reminder_id}/fire-now", status_code=status.HTTP_202_ACCEPTED)
async def fire_reminder_now(
    ngo_id: uuid.UUID,
    reminder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Immediately fire a reminder regardless of its schedule. Useful for testing."""
    reminder = await _get_reminder_or_404(reminder_id, ngo_id, db)

    if not reminder.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot fire an inactive reminder. Set is_active=True first.",
        )

    # Run synchronously within the request so the caller sees the outcome immediately.
    from app.scheduler.jobs.poll_reminders import fire_reminder

    await fire_reminder(reminder, db)

    logger.info(
        "reminder_fired_manually",
        reminder_id=str(reminder_id),
        ngo_id=str(ngo_id),
    )
    return {"detail": "Reminder fired", "reminder_id": str(reminder_id)}
