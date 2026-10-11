"""Arq worker settings — a separate process from the API (Rule #7).

``max_tries = 5`` is safe *only because* the job is idempotent.
Without the guards in :mod:`app.jobs`, retries would corrupt outputs.
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
    max_jobs = 4
    job_timeout = 1800
    keep_result = 3600
    max_tries = 5
