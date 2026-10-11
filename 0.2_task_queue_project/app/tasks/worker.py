# =====================================================================
# app/tasks/worker.py - ARQ Worker configuration (monolithic + micro)
# =====================================================================
# PURPOSE
# -------
# Defines the `WorkerSettings` classes ARQ's `arq` CLI looks for when
# you run `arq app.tasks.worker.WorkerSettings`. Each class is a recipe
# describing:
#   - which task FUNCTIONS the worker can execute
#   - which CRON jobs to schedule
#   - the REDIS connection
#   - resource HOOKS (on_startup/on_shutdown)
#   - tuning knobs (max_jobs, max_tries, timeouts, retain results)
#
# We provide ONE big class for monolithic deployments and several
# small classes for the microservice variant, each with its own
# `queue_name` so jobs can be routed to a specific worker pool.
# =====================================================================

import logging
from datetime import datetime, timezone

# `func` lets us override per-task settings (timeout, max_tries, etc.)
# without modifying the task definition itself.
from arq import func
# RedisSettings is the connection config ARQ needs to talk to Redis.
from arq.connections import RedisSettings
# AsyncClient is created once in on_startup, stored in ctx, and reused
# by every task that needs to make outbound HTTP calls (e.g. webhooks).
from httpx import AsyncClient

from app.config import settings

# Import every task function. The string name we use when enqueueing
# (e.g. "send_welcome_email") must match the Python __name__ here.
from app.tasks.email_tasks import send_welcome_email, send_report_email, send_batch_email
from app.tasks.image_tasks import generate_thumbnail, resize_image
from app.tasks.report_tasks import generate_pdf_report, generate_csv_export
from app.tasks.payment_tasks import process_payment, process_refund
from app.tasks.etl_tasks import run_data_pipeline, sync_external_data
from app.tasks.webhook_tasks import dispatch_webhook, retry_webhook
from app.tasks.notification_tasks import send_push_notification, batch_notify
# Cron descriptors (not bare functions) — already wrapped via cron(...).
from app.tasks.cleanup_tasks import cron_cleanup_sessions, cron_cleanup_old_jobs

logger = logging.getLogger(__name__)

# Shared by every WorkerSettings class below — the four REDIS_* env vars resolve once at import.
REDIS_SETTINGS = RedisSettings(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    database=settings.REDIS_DB,
)


async def on_worker_startup(ctx: dict):
    """Initialize shared resources when the worker starts.

    ARQ Feature: on_startup hook.
    Creates shared resources (HTTP client, service instances) that
    are available to all tasks via the ctx dict.
    """
    logger.info("Worker starting up - initializing shared resources")
    # One AsyncClient per worker process — its internal pool reuses
    # TCP connections across thousands of webhook dispatches.
    ctx["http_client"] = AsyncClient(timeout=30.0)
    # Stamp the boot time so tasks can include it in their logs/metrics.
    ctx["worker_started_at"] = datetime.now(timezone.utc).isoformat()


async def on_worker_shutdown(ctx: dict):
    """Clean up shared resources when the worker shuts down.

    ARQ Feature: on_shutdown hook.
    Properly closes connections and resources created in on_startup.
    """
    logger.info("Worker shutting down - cleaning up resources")
    # aclose() releases all pooled sockets — critical inside containers
    # so SIGTERM finishes within the grace period.
    await ctx["http_client"].aclose()


class WorkerSettings:
    """ARQ Worker Settings - Monolithic mode.

    All tasks are registered here. For microservice deployment,
    split this into separate WorkerSettings per service domain
    (see docker-compose.micro.yml for queue-based isolation).

    ARQ Features demonstrated:
    - on_startup/on_shutdown: Shared resource lifecycle management
    - functions: List of all registered task functions
    - func() wrapper: Per-task timeout, max_tries, keep_result config
    - cron_jobs: Scheduled recurring tasks
    - max_jobs: Maximum concurrent jobs (50 for production)
    - retry_jobs: Auto-retry on Retry exception
    - redis_settings: Connection configuration
    """

    # Lifecycle hooks (see functions above).
    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown

    # Master list of every task the worker can execute. Items can be
    # either bare functions (default settings) or func(fn, ...) wrappers
    # that override per-task config.
    functions = [
        send_welcome_email,
        send_report_email,
        send_batch_email,
        generate_thumbnail,
        # Resize gets a 24h result retention and only 3 retries.
        func(resize_image, keep_result=86400, max_tries=3),
        generate_pdf_report,
        generate_csv_export,
        # Payments cap at 3 attempts so we don't burn money on retries.
        func(process_payment, max_tries=3),
        process_refund,
        run_data_pipeline,
        sync_external_data,
        dispatch_webhook,
        retry_webhook,
        send_push_notification,
        batch_notify,
        # Same function exposed under a SECOND name with a longer
        # timeout — call as enqueue_job("generate_pdf_report_long", ...).
        func(generate_pdf_report, name="generate_pdf_report_long", timeout=600, keep_result=3600),
    ]

    # Scheduled tasks (defined via arq.cron() in cleanup_tasks.py).
    cron_jobs = [
        cron_cleanup_sessions,
        cron_cleanup_old_jobs,
    ]

    # Redis connection — built from the central settings.
    redis_settings = REDIS_SETTINGS

    max_jobs = 50              # Max concurrent jobs in this worker process.
    retry_jobs = True           # Honour `raise Retry(...)` exceptions.
    max_tries = 5               # Default cap on retries per task.
    job_timeout = 300           # Default timeout (5 min) — overridable via func().
    keep_result = 3600          # Default result retention (1 hour) in Redis.
    health_check_key = "arq:health:default"  # Key written periodically for liveness.


# --- MICROSERVICE MODE ------------------------------------------------
# Each of the classes below polls ONLY its own Redis queue and only
# registers the task functions relevant to its domain. The API routes
# use `_queue_name="email"|"payment"|"report"` to target them.


# 1. What max_jobs = 20 Does
# In a microservice deployment model, the WorkerSettingsEmail class defines a dedicated worker that listens only to the "email" queue. By setting max_jobs = 20, you are telling this email worker:

# "At any given moment, do not run more than 20 email tasks concurrently."

# If there are 100 emails in the queue, the worker will process 20 of them concurrently. As soon as one email task finishes, it will pick up the next one from the queue, maintaining a maximum concurrency of 20.


class WorkerSettingsEmail:
    """Worker for email service only - Microservice mode.

    ARQ Feature: Queue isolation with custom queue_name.
    Only processes email-related tasks from the "email" queue.
    """
    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown
    functions = [send_welcome_email, send_report_email, send_batch_email]
    queue_name = "email"  # Listens ONLY to this Redis sorted set.
    redis_settings = REDIS_SETTINGS
    # Lower concurrency than monolithic — email work is generally fast,
    # but limit prevents SMTP rate-limit issues.
    max_jobs = 20 # max_jobs controls the maximum number of concurrent tasks that a single worker instance will execute at any one time.


class WorkerSettingsPayment:
    """Worker for payment service only - Microservice mode."""
    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown
    # Same 3-try cap as monolithic — payments must not be retried indefinitely.
    functions = [func(process_payment, max_tries=3), process_refund]
    queue_name = "payment"
    redis_settings = REDIS_SETTINGS
    # Tight concurrency — many payment gateways throttle aggressively.
    max_jobs = 10


class WorkerSettingsReport:
    """Worker for report service only - Microservice mode."""
    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown
    # Reports also handle image work because image generation often
    # accompanies PDF rendering (e.g. embedded charts).
    functions = [generate_pdf_report, generate_csv_export, generate_thumbnail, func(resize_image, keep_result=86400, max_tries=3)]
    queue_name = "report"
    redis_settings = REDIS_SETTINGS
    # Report jobs are CPU/memory heavy — keep concurrency modest.
    max_jobs = 10
