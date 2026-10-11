# =====================================================================
# app/tasks/email_tasks.py - ARQ tasks for email delivery
# =====================================================================
# Each function below has the standard ARQ signature:
#     async def task(ctx: dict, *args) -> dict
# `ctx` is a per-worker dict that ARQ populates with:
#   - "redis"            : the ArqRedis pool (for enqueueing more jobs)
#   - "job_try"          : current attempt count (1-based)
#   - "job_id"           : the running job's id
#   - anything you stored in on_startup (e.g. http_client, services)
# =====================================================================

import json
import logging
from datetime import datetime, timezone

from arq.connections import ArqRedis  # Type hint for ctx["redis"].

from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


async def send_welcome_email(ctx: dict, user_id: int) -> dict:
    """Send a welcome email to a new user.

    ARQ Feature: Basic enqueue + _job_id for uniqueness.
    The API route can use _job_id=f"welcome_email_{user_id}"
    to prevent duplicate welcome emails.
    """
    logger.info("Sending welcome email for user_id=%s", user_id)
    # If on_startup stashed an EmailService into ctx, reuse it; otherwise
    # construct one on the fly. Reusing keeps any internal connections warm.
    email_service = ctx.get("email_service", EmailService())
    result = await email_service.send_welcome(user_id)
    logger.info("Welcome email sent for user_id=%s", user_id)
    # Merge our metadata with the service's return value (** spread).
    return {"user_id": user_id, "email_sent": True, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


async def send_report_email(ctx: dict, user_id: int, report_id: int) -> dict:
    """Send a report notification email to a user.

    ARQ Feature: Used with _defer_by to delay sending the email,
    e.g., enqueue_job('send_report_email', user_id, report_id, _defer_by=300)
    sends the email 5 minutes after the report is generated.
    """
    logger.info("Sending report email for user_id=%s, report_id=%s", user_id, report_id)
    email_service = ctx.get("email_service", EmailService())
    result = await email_service.send_report_notification(user_id, report_id)
    logger.info("Report email sent for user_id=%s, report_id=%s", user_id, report_id)
    return {"user_id": user_id, "report_id": report_id, "email_sent": True, **result}


async def send_batch_email(ctx: dict, user_ids: list[int], subject: str, body: str) -> dict:
    """Send emails to multiple users by fanning out individual tasks.

    ARQ Feature: Fan-out pattern - this task enqueues individual
    send_welcome_email tasks for each user, demonstrating task chaining.
    """
    # ctx["redis"] is the pool ARQ injects so tasks can enqueue more jobs.
    redis: ArqRedis = ctx["redis"]
    job_ids = []
    # One task per recipient → the worker pool processes them in parallel
    # up to WorkerSettings.max_jobs.
    for uid in user_ids:
        job = await redis.enqueue_job("send_welcome_email", uid)
        # enqueue_job returns None when _job_id collides; only track real jobs.
        if job:
            job_ids.append(job.job_id)
    logger.info("Batch email: enqueued %s individual welcome email tasks", len(job_ids))
    return {"total": len(user_ids), "enqueued": len(job_ids), "job_ids": job_ids}
