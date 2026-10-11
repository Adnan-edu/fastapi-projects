# =====================================================================
# app/api/jobs.py - Generic ARQ job enqueue / status / listing routes
# =====================================================================
# PURPOSE
# -------
# Exposes a low-level interface for enqueuing ANY registered ARQ task,
# checking its Redis-side status, and listing the persistent JobLog rows.
# Useful for admin / debugging UIs and for demonstrating the core
# enqueue+poll lifecycle.
# =====================================================================

import json
from datetime import datetime

# `Job` in arq.jobs lets us look up a job by id WITHOUT calling
# enqueue_job again. We pass it the redis pool + id.
from arq.jobs import Job as ArqJob
# FastAPI route + dependency primitives.
from fastapi import APIRouter, Depends, HTTPException
# SQLAlchemy select() builder + AsyncSession type for our DB dependency.
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local helpers and models.
from app.database import get_db
from app.arq_utils import get_redis_pool
from app.models import JobLog, JobStatus
from app.schemas.job import JobCreate, JobRead, JobStatusResponse

# All routes here are prefixed with /jobs and grouped under the "jobs"
# tag in the Swagger UI.
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/enqueue", response_model=JobRead)
async def enqueue_job(job_in: JobCreate, db: AsyncSession = Depends(get_db)):
    """Enqueue an ARQ task and track it in the database.

    ARQ Feature demonstrated: enqueue_job returns a Job object.
    The job_id is stored for later status tracking.
    """
    # Grab the singleton Redis pool — used to call enqueue_job below.
    redis = await get_redis_pool()

    # Build the optional kwargs dict. If the caller supplied an
    # idempotency_key, we pass it as ARQ's `_job_id` so duplicate
    # enqueues for the same key collapse into one job.
    kwargs = {}
    if job_in.idempotency_key:
        kwargs["_job_id"] = job_in.idempotency_key

    # Actually enqueue the task. `*_parse_input(...)` unpacks the JSON
    # input_data into positional task args. If the task name doesn't
    # exist on the worker, ARQ still queues it — the worker will fail
    # at execution time.
    arq_job = await redis.enqueue_job(job_in.task_name, *_parse_input(job_in.input_data), **kwargs)

    # Persist an audit row so we can list/inspect later via /jobs/.
    job_log = JobLog(
        arq_job_id=arq_job.job_id if arq_job else None,  # None if dedup collapsed
        task_name=job_in.task_name,
        status=JobStatus.PENDING,
        input_data=job_in.input_data,
    )
    db.add(job_log)
    await db.commit()
    # refresh() pulls back default-generated columns (id, created_at).
    await db.refresh(job_log)

    return job_log


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Check the status of an ARQ job.

    ARQ Feature demonstrated: job.status() and job.result().
    Shows how to poll for job results from the API layer.
    """
    redis = await get_redis_pool()
    # Reconstruct an ARQ Job handle by id — no DB hit, all from Redis.
    arq_job = ArqJob(job_id=job_id, redis=redis)

    # status() returns one of queued/in_progress/complete/not_found.
    status = await arq_job.status()
    result = None
    # If the job finished, try to read its return value. timeout=1
    # avoids hanging if the result has expired between status() and
    # result() (race condition with keep_result).
    if status.value == "complete":
        try:
            result = str(await arq_job.result(timeout=1))
        except Exception:
            # Swallow — result may have already been GC'd; we just
            # surface the status without the payload.
            result = None

    return JobStatusResponse(
        arq_job_id=job_id,
        status=status.value,
        result=result,
    )


@router.get("/", response_model=list[JobRead])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    # Return the most recent 50 audit rows, newest first.
    result = await db.execute(select(JobLog).order_by(JobLog.created_at.desc()).limit(50))
    return list(result.scalars().all())


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # Look up a single audit row by its UUID primary key.
    result = await db.execute(select(JobLog).where(JobLog.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# --- Private helper ----------------------------------------------------
def _parse_input(input_data: str | None) -> list:
    """Parse a JSON string of task args into a list.

    Accepts either a JSON array `[1, "foo"]` (used as *args) or a single
    JSON value `42` (wrapped in a one-element list). Returns [] on
    invalid JSON so callers can always *unpack the result.
    """
    if not input_data:
        return []
    try:
        parsed = json.loads(input_data)
        # An array becomes positional args directly.
        if isinstance(parsed, list):
            return parsed
        # Anything else is treated as a single positional arg.
        return [parsed]
    except json.JSONDecodeError:
        # Silently ignore bad JSON — the API contract is best-effort.
        return []
