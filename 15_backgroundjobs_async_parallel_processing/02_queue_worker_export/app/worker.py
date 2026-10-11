"""Arq worker entry point.

Run with:

    uv run arq app.worker.WorkerSettings
"""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from app.jobs import run_export


class WorkerSettings:
    redis_settings = RedisSettings(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )
    functions = [run_export]
    max_jobs = 4          # concurrent jobs per worker process
    job_timeout = 1800    # 30 min cap for big exports
