"""APScheduler engine singleton for the NGO OpsBot scheduler layer.

Started in main.py lifespan; other modules reference it via get_scheduler().
"""

from __future__ import annotations

import pytz
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton — started in main.py lifespan, referenced by reminder CRUD
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler not started — call start_scheduler() first")
    return _scheduler


async def start_scheduler() -> AsyncIOScheduler:
    global _scheduler  # noqa: PLW0603

    settings = get_settings()

    jobstores = {
        # MemoryJobStore avoids the synchronous Redis jobstore; state is rebuilt
        # from the DB on restart, which is fine for our poll-and-execute model.
        "default": MemoryJobStore(),
    }
    executors = {
        # AsyncIOExecutor lets async job functions run directly in the event loop.
        "default": AsyncIOExecutor(),
    }
    job_defaults = {
        # Prevents N identical runs when the poller wakes late after a restart.
        "coalesce": True,
        # Still run a job if it fires up to 60 s late (e.g. slow startup).
        "misfire_grace_time": 60,
    }

    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=pytz.timezone(settings.SCHEDULER_TIMEZONE),
    )

    # Lazy import avoids circular dependency at module load time.
    from app.scheduler.jobs.poll_reminders import (
        poll_due_reminders,
        update_active_ngos_gauge,
    )

    # Poll every 15 min; distributed lock inside the job prevents double-execution.
    _scheduler.add_job(
        poll_due_reminders,
        trigger=IntervalTrigger(minutes=15),
        id="poll_due_reminders",
        replace_existing=True,
    )

    # Gauge reflects live DB state; 5-min cadence is precise enough for dashboards.
    _scheduler.add_job(
        update_active_ngos_gauge,
        trigger=IntervalTrigger(minutes=5),
        id="update_active_ngos_gauge",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("scheduler_started", timezone=settings.SCHEDULER_TIMEZONE)
    return _scheduler


async def stop_scheduler() -> None:
    global _scheduler  # noqa: PLW0603
    if _scheduler is not None and _scheduler.running:
        # wait=True lets in-flight jobs complete cleanly before the process exits.
        _scheduler.shutdown(wait=True)
        logger.info("scheduler_stopped")
    _scheduler = None


async def add_reminder_job(reminder_id: str, cron_expr: str, timezone: str) -> None:
    """Add or replace a CronTrigger job for a single recurring reminder."""
    scheduler = get_scheduler()

    from app.scheduler.jobs.poll_reminders import fire_reminder_by_id

    # Deterministic job ID makes re-adding idempotent and handles reminder edits.
    job_id = f"reminder_{reminder_id}"

    try:
        tz = pytz.timezone(timezone)
    except Exception:
        # Fall back to UTC so a bad timezone string doesn't silently drop the job.
        logger.warning("invalid_reminder_timezone", reminder_id=reminder_id, timezone=timezone)
        tz = pytz.utc

    scheduler.add_job(
        fire_reminder_by_id,
        trigger=CronTrigger.from_crontab(cron_expr, timezone=tz),
        id=job_id,
        args=[reminder_id],
        replace_existing=True,
    )
    logger.info("reminder_job_added", reminder_id=reminder_id, cron=cron_expr, timezone=timezone)


async def remove_reminder_job(reminder_id: str) -> None:
    """Remove a reminder's APScheduler job silently if it exists."""
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("reminder_job_removed", reminder_id=reminder_id)
    except Exception:
        # Job may not exist (e.g. non-recurring reminder); silence is correct here.
        pass
