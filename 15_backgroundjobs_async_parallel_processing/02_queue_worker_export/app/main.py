"""FastAPI surface for Project 2.

Three endpoints only:

* ``POST /export`` — enqueue an export job and return a ``job_id``.
* ``GET /export/{job_id}`` — report Arq's job status, with a file-on-disk
  fallback for the case where Arq has aged the job metadata out.
* ``GET /export/{job_id}/file`` — stream the produced CSV.

The API process never touches Postgres directly — that's the worker's
job. This keeps API latency in single-digit milliseconds.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "exports"))
EXPORT_DIR.mkdir(exist_ok=True)


class ExportRequest(BaseModel):
    status: str | None = None
    country: str | None = None
    customer_id: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests pre-populate ``app.state.redis`` with a fake pool and skip
    # this branch. In production we open a real Arq pool here.
    if getattr(app.state, "redis", None) is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        app.state.redis = await create_pool(
            RedisSettings(
                host=os.environ.get("REDIS_HOST", "localhost"),
                port=int(os.environ.get("REDIS_PORT", "6379")),
            )
        )
    try:
        yield
    finally:
        # Only close pools we opened (i.e. real Arq pools, not test fakes).
        pool = getattr(app.state, "redis", None)
        close = getattr(pool, "close", None)
        if callable(close):
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass


app = FastAPI(title="Project 2 — Queue + Worker Export", lifespan=lifespan)


@app.post("/export")
async def start_export(req: ExportRequest) -> dict:
    job_id = str(uuid.uuid4())
    await app.state.redis.enqueue_job(
        "run_export",
        job_id,
        req.model_dump(),
        _job_id=job_id,
    )
    return {"job_id": job_id, "status": "queued"}


async def _lookup_job(redis, job_id: str):
    """Return a job handle from either a real Arq pool or a test fake.

    The Arq ``ArqRedis`` pool itself doesn't expose ``.job(id)``; you
    construct an ``arq.jobs.Job`` against the pool. Our test fake does
    expose ``.job(id)`` to record lookups, so we honour both shapes.
    """

    fake = getattr(redis, "job", None)
    if callable(fake):
        return await fake(job_id)
    from arq.jobs import Job

    return Job(job_id, redis)


@app.get("/export/{job_id}")
async def export_status(job_id: str) -> dict:
    job = await _lookup_job(app.state.redis, job_id)
    info = await job.info() if job is not None else None
    if info is None:
        # Arq drops job metadata after a TTL — fall back to file
        # presence so a completed job that's been forgotten still
        # reports as ``done``.
        path = EXPORT_DIR / f"{job_id}.csv"
        if path.exists():
            return {
                "job_id": job_id,
                "status": "done",
                "size": path.stat().st_size,
            }
        raise HTTPException(404, "unknown job")

    # ``info()`` returns ``JobDef`` while queued/in-progress and
    # ``JobResult`` once finished. They don't share an attribute set —
    # for ``JobResult`` the ``.status`` we want is on the enum returned
    # by ``Job.status()``. We fish out the value defensively.
    status = getattr(info, "status", None)
    if status is None and hasattr(job, "status"):
        status = await job.status()
    status_value = getattr(status, "value", status)
    enqueue_time = getattr(info, "enqueue_time", None)
    payload = {"job_id": job_id, "status": status_value}
    if enqueue_time is not None:
        payload["enqueue_time"] = (
            enqueue_time.timestamp() if hasattr(enqueue_time, "timestamp") else enqueue_time
        )
    if status_value == "complete":
        path = EXPORT_DIR / f"{job_id}.csv"
        if path.exists():
            payload["size"] = path.stat().st_size
    return payload


@app.get("/export/{job_id}/file")
async def export_file(job_id: str) -> FileResponse:
    path = EXPORT_DIR / f"{job_id}.csv"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}.csv")
