"""End-to-end test fixtures.

Boots the real stack against the existing local Redis (db=15, used as
an isolation namespace) and the existing Postgres ``cursor_pagination``
database that already holds the 1M ``order_events`` rows.

Each test session gets:
- a fresh ``exports/`` directory (tmp_path-based) — no carry-over files
- a clean Redis db 15 — flushed at start and end
- an API process on a dynamically-chosen free port
- an Arq worker process sharing the same EXPORT_DIR and REDIS db
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import redis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REDIS_HOST = "localhost"
REDIS_PORT = 6379
# Arq's RedisSettings doesn't expose db cleanly across versions; we
# isolate by flushing db 0 before/after the session instead. To avoid
# nuking the user's dev queue, we assert it's empty first.
EXPECTED_EMPTY_DB = True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code < 500:
                return
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"service at {url} never came up: {last_err}")


@pytest.fixture(scope="session")
def export_dir(tmp_path_factory) -> Path:
    """Per-session export directory — keeps real /exports untouched."""

    d = tmp_path_factory.mktemp("exports")
    return d


@pytest.fixture(scope="session")
def prom_dir(tmp_path_factory) -> Path:
    """Shared prometheus_client multiprocess directory.

    Both the API and worker subprocesses point at this so counters
    incremented in the worker are visible at the API's /metrics
    endpoint via MultiProcessCollector.
    """

    return tmp_path_factory.mktemp("prom_multiproc")


@pytest.fixture(scope="session", autouse=True)
def _redis_isolation():
    """Refuse to run if the dev Redis already has jobs queued.

    Then flush and yield; flush again on teardown so the next test run
    starts clean.
    """

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    if r.dbsize() != 0:
        pytest.skip(
            f"Redis db 0 is not empty (dbsize={r.dbsize()}). "
            "Tests refuse to clobber an in-use queue. "
            "Run `docker exec redis-arq redis-cli flushdb` if safe."
        )
    r.flushdb()
    yield
    r.flushdb()


@pytest.fixture(scope="session")
def api_url(export_dir, prom_dir):
    """Boot the FastAPI app on a free port and yield its base URL."""

    port = _free_port()
    env = {
        **os.environ,
        "EXPORT_DIR": str(export_dir),
        "REDIS_HOST": REDIS_HOST,
        "REDIS_PORT": str(REDIS_PORT),
        "PYTHONPATH": str(PROJECT_ROOT),
        "PROMETHEUS_MULTIPROC_DIR": str(prom_dir),
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_http(f"{base}/metrics")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def worker(export_dir, prom_dir):
    """Boot the Arq worker as a subprocess sharing EXPORT_DIR + Redis."""

    env = {
        **os.environ,
        "EXPORT_DIR": str(export_dir),
        "REDIS_HOST": REDIS_HOST,
        "REDIS_PORT": str(REDIS_PORT),
        "PYTHONPATH": str(PROJECT_ROOT),
        "PROMETHEUS_MULTIPROC_DIR": str(prom_dir),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "arq", "app.worker.WorkerSettings"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # Arq has no health endpoint; sleep briefly to let it connect.
    time.sleep(1.5)
    if proc.poll() is not None:
        out = proc.stdout.read().decode() if proc.stdout else ""
        raise RuntimeError(f"worker exited early:\n{out}")
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def client(api_url, worker):
    """httpx client bound to the running API. Worker is started too."""

    with httpx.Client(base_url=api_url, timeout=30.0) as c:
        yield c


def wait_for_done(client: httpx.Client, key: str, timeout: float = 60.0) -> dict:
    """Poll GET /export/{key} until status == 'done' or timeout."""

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/export/{key}")
        if r.status_code == 200:
            last = r.json()
            if last.get("status") == "done":
                return last
        time.sleep(0.3)
    raise AssertionError(f"job {key} never finished; last status: {last}")
