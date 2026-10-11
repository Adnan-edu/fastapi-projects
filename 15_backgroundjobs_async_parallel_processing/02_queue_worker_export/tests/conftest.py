"""Shared fixtures.

The API talks to Arq through a Redis pool stored on ``app.state.redis``.
For unit tests we never bring up Redis; we install a fake pool that
records ``enqueue_job`` calls and serves scripted ``job(...)`` lookups.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# These env vars are read by app.jobs at import time. Tests never connect
# to the real DB, but the symbol must exist.
os.environ.setdefault(
    "ASYNCPG_DSN", "postgresql://test:test@localhost:5432/test"
)


@dataclass
class FakeJobInfo:
    status: str = "in_progress"
    enqueue_time: float = 0.0


@dataclass
class FakeJob:
    """Mirror of ``arq.jobs.Job`` — only the bits the endpoint uses."""

    info_payload: FakeJobInfo | None = field(default_factory=FakeJobInfo)

    async def info(self) -> FakeJobInfo | None:
        return self.info_payload


@dataclass
class FakeRedisPool:
    """Stand-in for the Arq pool. Records what got enqueued and what
    ``job(job_id)`` should return."""

    enqueued: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, FakeJob] = field(default_factory=dict)

    async def enqueue_job(self, function_name, *args, _job_id=None, **kwargs):
        self.enqueued.append(
            {"function": function_name, "args": args, "job_id": _job_id, "kwargs": kwargs}
        )
        # default: job is queued and discoverable afterwards
        self.jobs.setdefault(_job_id, FakeJob())
        return self.jobs[_job_id]

    async def job(self, job_id):
        # Arq returns a Job object regardless; .info() may return None.
        return self.jobs.get(job_id, FakeJob(info_payload=None))


@pytest.fixture
def fake_pool() -> FakeRedisPool:
    return FakeRedisPool()


@pytest.fixture
def export_dir(tmp_path, monkeypatch) -> Path:
    """Redirect ``EXPORT_DIR`` to a tmp directory for the API and jobs."""
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "EXPORT_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(fake_pool, export_dir):
    """TestClient with the Arq pool stubbed."""
    from app.main import app

    # Skip the real ``create_pool`` lifespan by pre-populating app.state.
    app.state.redis = fake_pool
    with TestClient(app) as c:
        c.fake_pool = fake_pool  # type: ignore[attr-defined]
        c.export_dir = export_dir  # type: ignore[attr-defined]
        yield c
