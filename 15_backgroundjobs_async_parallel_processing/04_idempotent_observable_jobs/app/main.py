"""FastAPI surface — HTTP only.

Per Rule #7, this process never opens a Postgres connection and never
runs CPU-heavy work. It enqueues jobs into Redis and reports their
state. The worker (a different process) does the export.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import JobStatus
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from pydantic import BaseModel

from app.ids import idempotency_key
from app.log_setup import log
# Importing app.metrics here serves two purposes: (1) under single-process
# mode the metric families register with the API's default REGISTRY so
# /metrics emits the HELP/TYPE lines even before any worker job has run;
# (2) under multiprocess mode the import is harmless — actual values
# still come from MultiProcessCollector below.
from app import metrics as _metrics  # noqa: F401  (side-effect import)

REDIS = RedisSettings(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
)
EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "exports"))
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Same whitelist as jobs.py — keep them in sync. Duplicated rather than
# imported so the API can validate before enqueueing.
FILTER_COLUMNS = ("status", "country", "customer_id")


class ExportRequest(BaseModel):
    """Body of POST /export.

    Unknown keys are accepted but ignored by ``model_dump`` because
    they aren't declared. SQL injection vector closed at the model
    boundary.
    """

    status: str | None = None
    country: str | None = None
    customer_id: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one Redis pool for the API process's lifetime."""

    app.state.redis = await create_pool(REDIS)
    try:
        yield
    finally:
        await app.state.redis.close()


app = FastAPI(title="Project 4 — Idempotent & Observable Jobs", lifespan=lifespan)


def _clean_filters(req: ExportRequest) -> dict:
    """Strip ``None`` values — see :func:`app.ids.idempotency_key`."""

    return {k: v for k, v in req.model_dump().items() if v is not None}


@app.post("/export")
async def start_export(req: ExportRequest):
    """Enqueue (or report a cached) export."""

    filters = _clean_filters(req)
    key = idempotency_key(filters)
    path = EXPORT_DIR / f"{key}.csv"

    if path.exists():
        log.info("export.cache_hit", key=key)
        return {"key": key, "status": "done", "cached": True}

    # ``_job_id=key`` ensures Arq treats two identical submissions as the
    # same job — the second enqueue is a no-op while the first is still
    # running.
    await app.state.redis.enqueue_job("run_export", filters, _job_id=key)
    return {"key": key, "status": "queued"}


@app.get("/export/{key}")
async def export_status(key: str):
    """Report job status. Disk check first — once the file exists, the
    job is definitively done regardless of what Redis still has."""

    path = EXPORT_DIR / f"{key}.csv"
    if path.exists():
        return {"key": key, "status": "done", "size": path.stat().st_size}

    from arq.jobs import Job

    job = Job(key, redis=app.state.redis)
    status = await job.status()
    if status == JobStatus.not_found:
        raise HTTPException(404, "unknown key")
    return {"key": key, "status": status.value}


@app.get("/export/{key}/file")
async def download(key: str):
    """Stream the finished CSV. 404 until the atomic rename has landed."""

    path = EXPORT_DIR / f"{key}.csv"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="text/csv", filename=f"{key}.csv")


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint.

    If ``PROMETHEUS_MULTIPROC_DIR`` is set, we aggregate values across
    every process that has written to that directory — that is how the
    API can expose counters incremented by the worker. Otherwise we
    fall back to the default in-process registry.
    """

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)
