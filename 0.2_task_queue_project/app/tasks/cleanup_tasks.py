# =====================================================================
# app/tasks/cleanup_tasks.py - Cron-driven housekeeping tasks
# =====================================================================
# Two scheduled jobs that prune old JobLog rows on a cadence:
#   - cleanup_expired_sessions : hourly + at worker startup
#   - cleanup_old_job_results  : daily at 2am
# Both use unique=True so multiple workers can't run the same cleanup
# at the same time — Redis acts as the lock.
# =====================================================================

import logging
from datetime import datetime, timezone, timedelta

# `cron` wraps an async function into a CronJob descriptor that
# WorkerSettings.cron_jobs lists. ARQ then schedules it.
from arq import cron

from app.database import async_session
from app.models import JobLog, JobStatus, Payment, PaymentStatus, Report, ReportStatus

logger = logging.getLogger(__name__)


async def cleanup_expired_sessions(ctx: dict) -> dict:
    """Cron job: Clean up expired sessions and stale data.

    ARQ Feature: @cron decorator with run_at_startup=True.
    This task runs automatically at scheduled times (every hour)
    and also runs once when the worker starts up.
    """
    logger.info("Running cleanup_expired_sessions cron job")
    # Open our own DB session — cron tasks don't get one in ctx by default.
    async with async_session() as session:
        # Cut-off: anything completed more than 24h ago is expendable.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Bulk DELETE via a core SQL statement — far faster than ORM
        # iteration when removing many rows.
        result = await session.execute(
            JobLog.__table__.delete().where(
                JobLog.completed_at.isnot(None),
                JobLog.completed_at < cutoff,
            )
        )
        # rowcount tells us how many rows were affected; guard with
        # hasattr because some drivers don't populate it.
        expired_count = result.rowcount if hasattr(result, "rowcount") else 0
        await session.commit()

    logger.info("Cleanup: removed %s expired session records", expired_count)
    return {"expired_sessions_removed": expired_count, "timestamp": datetime.now(timezone.utc).isoformat()}


async def cleanup_old_job_results(ctx: dict) -> dict:
    """Cron job: Clean up old job results from the database.

    ARQ Feature: @cron decorator with unique=True.
    Ensures only one cleanup runs at a time, even with multiple workers.
    Runs daily at 2 AM.
    """
    logger.info("Running cleanup_old_job_results cron job")
    async with async_session() as session:
        # Longer retention: 30 days. This is the "really gone" cleanup.
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = await session.execute(
            JobLog.__table__.delete().where(
                JobLog.completed_at.isnot(None),
                JobLog.completed_at < cutoff,
            )
        )
        old_count = result.rowcount if hasattr(result, "rowcount") else 0
        await session.commit()

    logger.info("Cleanup: removed %s old job results", old_count)
    return {"old_jobs_removed": old_count, "timestamp": datetime.now(timezone.utc).isoformat()}


# --- CronJob descriptors ----------------------------------------------
# `cron(func, ...)` wraps the function and returns a CronJob ARQ
# understands. These objects are then listed in WorkerSettings.cron_jobs.
#
# `hour="*", minute=0`  -> every hour on the minute
# `run_at_startup=True` -> also fire once immediately on worker start
# `unique=True`         -> Redis lock; no two workers run it concurrently
cron_cleanup_sessions = cron(cleanup_expired_sessions, hour="*", minute=0, run_at_startup=True, unique=True)

# `hour=2, minute=0`    -> daily at 02:00 (low-traffic window)
cron_cleanup_old_jobs = cron(cleanup_old_job_results, hour=2, minute=0, unique=True)
