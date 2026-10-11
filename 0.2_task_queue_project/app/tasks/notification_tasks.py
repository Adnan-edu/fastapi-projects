# =====================================================================
# app/tasks/notification_tasks.py - ARQ tasks for push notifications
# =====================================================================
# Showcases the classic FAN-OUT pattern: one orchestrating task
# (batch_notify) spawns N independent worker tasks (send_push_notification)
# that ARQ executes in parallel up to WorkerSettings.max_jobs.
# =====================================================================

import logging
from datetime import datetime, timezone

from arq.connections import ArqRedis

from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def send_push_notification(ctx: dict, user_id: int, message: str) -> dict:
    """Send a push notification to a user.

    ARQ Feature: Basic fire-and-forget task.
    The simplest ARQ pattern: enqueue a task and don't wait for result.
    The worker picks it up and processes it asynchronously.
    """
    logger.info("Sending push notification to user_id=%s", user_id)
    notification_service = ctx.get("notification_service", NotificationService())
    result = await notification_service.send_push(user_id, message)
    logger.info("Push notification sent to user_id=%s", user_id)
    return {"user_id": user_id, "message": message, "sent": True, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


async def batch_notify(ctx: dict, user_ids: list[int], message: str) -> dict:
    """Send notifications to multiple users by fanning out individual tasks.

    ARQ Feature: Fan-out pattern.
    This task enqueues an individual send_push_notification task
    for each user in the batch, demonstrating how one task can
    trigger many sub-tasks for parallel processing.
    """
    logger.info("Batch notify: %s users", len(user_ids))
    redis: ArqRedis = ctx["redis"]
    job_ids = []
    # One child job per user. The receiving worker decides parallelism
    # via max_jobs — there's no need for us to throttle here.
    for uid in user_ids:
        job = await redis.enqueue_job("send_push_notification", uid, message)
        # enqueue_job returns None if a job with the same _job_id already
        # exists (dedup). We only track the ones we actually queued.
        if job:
            job_ids.append(job.job_id)
    logger.info("Batch notify: enqueued %s push notification tasks", len(job_ids))
    return {"total_users": len(user_ids), "enqueued": len(job_ids), "job_ids": job_ids, "timestamp": datetime.now(timezone.utc).isoformat()}
