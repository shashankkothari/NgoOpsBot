"""Core scheduler job: poll DB for due reminders and fire them.

Also owns the helper functions for evaluating reminder conditions and
computing the next fire time — re-exported via reminder_types.py for clarity.
"""

from __future__ import annotations

import operator as op
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select

from app.core.cache import get_redis
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.metrics import active_ngos, reminders_sent
from app.models.conversation import ConversationThread
from app.models.ngo import NGO
from app.models.reminder import Reminder, ReminderLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# Redis key for the distributed poll lock; TTL slightly under the 15-min interval.
_POLL_LOCK_KEY = "lock:scheduler:poll"
_POLL_LOCK_TTL_SECONDS = 14 * 60

# Maps string operators from threshold config to Python operator functions.
_OPERATORS = {
    "<": op.lt,
    "<=": op.le,
    ">": op.gt,
    ">=": op.ge,
    "==": op.eq,
    "!=": op.ne,
}


async def poll_due_reminders() -> None:
    """Main poller: find all reminders with next_fire_at <= now and execute them."""
    redis = await get_redis()

    # SET NX EX implements a distributed lock without a Lua script.
    acquired = await redis.set(_POLL_LOCK_KEY, "1", nx=True, ex=_POLL_LOCK_TTL_SECONDS)
    if not acquired:
        # Another replica is already polling; skip to avoid double-sends.
        logger.debug("scheduler_poll_lock_busy")
        return

    logger.info("scheduler_poll_started")
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Reminder)
            .join(NGO, Reminder.ngo_id == NGO.id)
            .where(
                Reminder.is_active.is_(True),
                Reminder.next_fire_at <= now,
                # Exclude event_triggered — those are fired by agent code, not the poller.
                Reminder.reminder_type != "event_triggered",
                NGO.is_active.is_(True),
            )
        )
        reminders = result.scalars().all()

    logger.info("scheduler_poll_due_count", count=len(reminders))

    for reminder in reminders:
        # Each reminder gets its own session so one failure never rolls back others.
        async with AsyncSessionLocal() as db:
            await fire_reminder(reminder, db)


async def fire_reminder(reminder: Reminder, db: AsyncSession) -> None:
    """Execute one reminder end-to-end; catch all exceptions so the poller continues."""
    from app.agents.comms import draft_reminder_message
    from app.scheduler.jobs.send_reminder import send_approval_request, send_to_staff_group

    try:
        # Reload reminder and NGO inside the session to ensure fresh state.
        result = await db.execute(select(Reminder).where(Reminder.id == reminder.id))
        reminder = result.scalar_one()

        ngo_result = await db.execute(select(NGO).where(NGO.id == reminder.ngo_id))
        ngo = ngo_result.scalar_one()

        should_fire, context = await _evaluate_condition(reminder, ngo, db)
        if not should_fire:
            logger.info(
                "reminder_condition_false",
                reminder_id=str(reminder.id),
                ngo_slug=ngo.slug,
            )
            # Still advance the next_fire_at so we check again at the right interval.
            reminder.next_fire_at = _calculate_next_fire_at(reminder)
            await db.commit()
            return

        message_text = await draft_reminder_message(reminder, ngo, context, ngo.language)

        now = datetime.now(timezone.utc)

        # Determine the delivery channel: telegram for group sends, else from config.
        sent_via = _determine_channel(reminder)

        log = ReminderLog(
            reminder_id=reminder.id,
            ngo_id=reminder.ngo_id,
            fired_at=now,
            status="pending",
            content=message_text,
            sent_via=sent_via,
        )
        db.add(log)
        await db.flush()  # get log.id before routing

        if reminder.target_audience == "staff_group":
            success = await send_to_staff_group(ngo, reminder, message_text)
            log.status = "sent" if success else "failed"
            if not success:
                log.error_message = "Telegram send returned None"
            else:
                reminders_sent.labels(ngo_slug=ngo.slug, channel="telegram").inc()

        elif reminder.target_audience in ("external", "specific_staff"):
            if reminder.requires_approval:
                # Route to group for admin approval; actual send happens in callback_handler.
                success = await send_approval_request(
                    ngo, reminder, str(log.id), message_text
                )
                log.status = "pending_approval" if success else "failed"
                if not success:
                    log.error_message = "Failed to send approval request to Telegram group"
            else:
                # No approval needed — dispatch immediately.
                from app.comms.dispatcher import CommsChannel, send_reminder_to_target

                channel_enum = CommsChannel(sent_via)
                success = await send_reminder_to_target(channel_enum, message_text, reminder, ngo, db)
                log.status = "sent" if success else "failed"
                if not success:
                    log.error_message = f"Comms dispatcher failed for channel={sent_via}"
                else:
                    reminders_sent.labels(ngo_slug=ngo.slug, channel=sent_via).inc()

        reminder.last_fired_at = now
        reminder.next_fire_at = _calculate_next_fire_at(reminder)

        if reminder.reminder_type == "date_based":
            # One-shot reminder; deactivate so it never fires again.
            reminder.is_active = False

        await db.commit()
        logger.info(
            "reminder_fired",
            reminder_id=str(reminder.id),
            ngo_slug=ngo.slug,
            status=log.status,
        )

    except Exception as exc:
        # Never propagate — a broken reminder must not crash the entire poll cycle.
        logger.exception(
            "reminder_fire_error",
            reminder_id=str(reminder.id),
            error=str(exc),
        )
        try:
            await db.rollback()
        except Exception:
            pass


async def fire_reminder_by_id(reminder_id: str) -> None:
    """Entry point for APScheduler CronTrigger jobs on individual recurring reminders."""
    import uuid as _uuid

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Reminder).where(Reminder.id == _uuid.UUID(reminder_id))
        )
        reminder = result.scalar_one_or_none()
        if reminder is None or not reminder.is_active:
            logger.warning("reminder_job_not_found_or_inactive", reminder_id=reminder_id)
            return
        await fire_reminder(reminder, db)


async def _evaluate_condition(
    reminder: Reminder,
    ngo: NGO,
    db: AsyncSession,
) -> tuple[bool, dict]:
    """Evaluate whether this reminder should actually fire right now."""
    rtype = reminder.reminder_type
    config = reminder.config or {}

    if rtype in ("date_based", "recurring"):
        # Time-based types always fire when the scheduler says it's time.
        return True, {"title": reminder.title, "type": rtype}

    if rtype == "inactivity":
        agent_name = config.get("agent_name", "")
        inactive_days = int(config.get("inactive_days", 3))
        cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)

        result = await db.execute(
            select(ConversationThread)
            .where(
                ConversationThread.ngo_id == ngo.id,
                ConversationThread.agent_name == agent_name,
            )
            .order_by(ConversationThread.last_activity_at.desc())
            .limit(1)
        )
        thread = result.scalar_one_or_none()

        # Fire if no thread exists at all or if the last activity is beyond the threshold.
        if thread is None or thread.last_activity_at < cutoff:
            last_active = thread.last_activity_at.isoformat() if thread else "never"
            return True, {
                "agent_name": agent_name,
                "inactive_days": inactive_days,
                "last_active": last_active,
            }
        return False, {}

    if rtype == "threshold":
        return await _evaluate_threshold(reminder, ngo)

    # Unrecognised type or event_triggered — skip silently.
    logger.warning("reminder_unknown_type", reminder_id=str(reminder.id), rtype=rtype)
    return False, {}


async def _evaluate_threshold(
    reminder: Reminder,
    ngo: NGO,
) -> tuple[bool, dict]:
    """Read a Google Sheet column, aggregate it, and compare to the threshold."""
    from google.auth.exceptions import RefreshError

    from app.integrations.google.auth import get_credentials
    from app.integrations.google.sheets import read_tab

    config = reminder.config or {}
    sheet_tab = config.get("sheet_tab", "")
    column = config.get("column", "")
    aggregate = config.get("aggregate", "sum").lower()
    operator_str = config.get("operator", "<")
    threshold_value = float(config.get("value", 0))

    if not ngo.google_refresh_token or not ngo.google_master_sheet_id:
        # Can't evaluate without Google credentials or a sheet — skip gracefully.
        logger.warning(
            "reminder_threshold_no_google",
            reminder_id=str(reminder.id),
            ngo_slug=ngo.slug,
        )
        return False, {}

    try:
        creds = await get_credentials(ngo.google_refresh_token)
        rows = await read_tab(ngo.google_master_sheet_id, sheet_tab, creds, ngo.slug)
    except RefreshError:
        # Expired Google token — log and skip rather than crashing the poll cycle.
        logger.warning(
            "reminder_threshold_google_auth_error",
            reminder_id=str(reminder.id),
            ngo_slug=ngo.slug,
        )
        return False, {}

    if not rows:
        current_value = 0.0
    else:
        values: list[float] = []
        for row in rows:
            raw = row.get(column, "")
            try:
                values.append(float(str(raw).replace(",", "").strip()))
            except (ValueError, TypeError):
                pass

        if aggregate == "sum":
            current_value = sum(values)
        elif aggregate == "count":
            current_value = float(len(values))
        elif aggregate == "avg":
            current_value = sum(values) / len(values) if values else 0.0
        else:
            current_value = sum(values)

    compare = _OPERATORS.get(operator_str, op.lt)
    should_fire = compare(current_value, threshold_value)

    context = {
        "current_value": current_value,
        "threshold": threshold_value,
        "operator": operator_str,
        "column": column,
        "tab": sheet_tab,
    }
    return should_fire, context


def _calculate_next_fire_at(reminder: Reminder) -> Optional[datetime]:
    """Compute the next scheduled execution time for a reminder after it fires."""
    config = reminder.config or {}
    rtype = reminder.reminder_type
    now = datetime.now(timezone.utc)

    if rtype == "date_based":
        # One-shot; caller sets is_active=False — no next fire time needed.
        return None

    if rtype == "recurring":
        cron_expr = config.get("cron", "")
        tz_str = config.get("timezone", "UTC")
        if not cron_expr:
            return None
        try:
            import pytz
            tz = pytz.timezone(tz_str)
        except Exception:
            import pytz
            tz = pytz.utc
        trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
        # APScheduler returns the next fire time in the trigger's timezone; convert to UTC.
        next_dt = trigger.get_next_fire_time(None, now)
        if next_dt is None:
            return None
        return next_dt.astimezone(timezone.utc)

    if rtype == "inactivity":
        inactive_days = int(config.get("inactive_days", 3))
        # Re-check after the same idle period to avoid spamming.
        return now + timedelta(days=inactive_days)

    if rtype == "threshold":
        # Daily re-check is frequent enough for financial thresholds.
        return now + timedelta(days=1)

    # event_triggered reminders have no scheduler-driven next time.
    return None


def _determine_channel(reminder: Reminder) -> str:
    """Pick the delivery channel string for the ReminderLog from reminder config."""
    if reminder.target_audience == "staff_group":
        return "telegram"
    # External / specific_staff: prefer explicit channel in target_details.
    details = reminder.target_details or {}
    if details.get("emails"):
        return "email"
    if details.get("phones"):
        return "sms"
    if details.get("chat_id") or details.get("telegram_id"):
        return "telegram"
    # Default to telegram for Telegram-first platform.
    return "telegram"


async def update_active_ngos_gauge() -> None:
    """Count active NGO tenants and update the Prometheus gauge. Runs every 5 min."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count()).select_from(NGO).where(NGO.is_active.is_(True))
            )
            count = result.scalar_one()
        active_ngos.set(count)
        logger.debug("active_ngos_gauge_updated", count=count)
    except Exception as exc:
        # Gauge update failure is non-fatal — log and continue.
        logger.error("active_ngos_gauge_error", error=str(exc))
