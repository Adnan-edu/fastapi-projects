# 04 — Idempotent & Observable Jobs (Production)

> **Pattern:** Project 02 + idempotency key + atomic writes + structlog + Prometheus
> **File:** `04_idempotent_observable_jobs.md` (formerly `project_4.md`)

**Source rules:** Rule #7 (lines 258–289), Rule #8 (lines 291–318), and the Observability section (lines 321–348) of `backgroundjobs_async_parallel_processing_part_2.md`.

**Goal:** Take the queue + worker design from Project 2 and harden it for **production**. Add:

1. **Idempotency** — a job that runs twice produces the same result (Rule #8)
2. **Worker / API pool separation** — no shared process pool (Rule #7)
3. **Observability** — structured logs and metrics for queue depth, duration, failures

> This project deliberately reuses Project 2's code. The new parts are clearly marked **(NEW)** below. If you already built Project 2, you can layer these changes on top of it instead of starting from scratch.

---

## Dataset context

Same shared dataset at `/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils`:

- 1M-row `order_events` table
- Job: export filtered rows to CSV — exactly as in Project 2
- The **idempotency key** is derived from the filter set, not from a random UUID. This is what makes retries safe.

Why this matters at scale on this dataset:

- An export over `{status: paid, country: US}` produces a deterministic file. Retrying after a worker crash should reuse the file, not generate a second one.
- A 1M-row source is large enough that wasteful re-runs cost real CPU and disk.

---

## Architecture

```
                            ┌───────────────────────┐
   Client ──► FastAPI ──►   │  Redis (queue + meta) │
                            └─────────┬─────────────┘
                                      │
                  ┌───────────────────┴────────────────┐
                  │                                    │
            Worker pool A                        Worker pool B
            (CPU-heavy exports)                  (CPU-heavy exports)
                  │                                    │
                  └────► /exports/<idempotency_key>.csv (shared)

API workers and job workers NEVER share a process pool.
```

---

## Step 1 — Virtual environment with `uv`

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects
mkdir -p project_4_production_jobs && cd project_4_production_jobs

uv init --python 3.12
uv add fastapi 'uvicorn[standard]' sqlalchemy asyncpg arq redis \
       structlog prometheus-client pydantic-settings
```

`structlog` gives us JSON logs; `prometheus-client` exposes worker metrics.

---

## Step 2 — Start Redis, then verify data (ingest only if needed)

### 2a. Redis

```bash
docker run -d --name redis-prod -p 6379:6379 redis:7-alpine
```

### 2b. Verify the Postgres data — don't blindly re-ingest

Postgres state is persisted in a **Docker volume**; the 1M rows survive `docker compose down`. Idempotency is the whole point of Project 4, and that principle applies to *setup* too: re-running ingestion on a complete table is the same anti-pattern the export job is built to avoid. So we **check, then conditionally ingest**.

Use the shared `utils/check_ingested.py` (created in Project 1, Step 2a — one copy serves all four projects).

Exit codes:
- `0` → 1,000,000 rows present → **skip ingest**
- `1` → missing / empty / partial → ingest (resumable via `MAX(id)`)
- `2` → DB connection failed

### 2c. Conditional ingestion

```bash
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"
export CSV_PATH="/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/data/order_events_1m.csv"

uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py \
  && echo "data ready — skipping ingest" \
  || uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/ingest_order_events.py
```

> Production parallel: this check is the same shape as the in-job idempotency guard in Step 7 (`if out.exists(): return`). The principle — *verify state, do not duplicate work* — applies to both data ingestion and job execution.

---

## Step 3 — Layout

```
project_4_production_jobs/
├── pyproject.toml
├── exports/
└── app/
    ├── main.py        # API (HTTP only — see Rule #7)
    ├── worker.py      # Worker settings (separate process)
    ├── jobs.py        # Idempotent export job
    ├── ids.py         # (NEW) idempotency key derivation
    ├── logging.py     # (NEW) structured logging
    └── metrics.py     # (NEW) prometheus counters/histograms
```

---

## Step 4 — Idempotency key (NEW)

```python
# app/ids.py
import hashlib
import json

def idempotency_key(filters: dict) -> str:
    """Stable hash of normalized filters. Same input → same key → same output file."""
    canonical = json.dumps(filters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

---

## Step 5 — Structured logging (NEW)

```python
# app/logging.py
import logging
import structlog

logging.basicConfig(level=logging.INFO, format="%(message)s")

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger()
```

---

## Step 6 — Metrics (NEW)

```python
# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge

JOBS_STARTED   = Counter("export_jobs_started_total",   "Export jobs started",   ["status_filter"])
JOBS_COMPLETED = Counter("export_jobs_completed_total", "Export jobs completed", ["outcome"])
JOB_DURATION   = Histogram("export_job_duration_seconds","Export duration seconds")
QUEUE_DEPTH    = Gauge("export_queue_depth",            "Pending export jobs")
```

---

## Step 7 — Idempotent job (Rule #8, article lines 303–311)

The article's pattern:

```python
def export_job(job_id: str):
    if export_exists(job_id):
        return  # already done
    data = fetch_data(job_id)
    write_export(job_id, data)
```

Concrete version for `order_events`:

```python
# app/jobs.py
import csv
import time
from pathlib import Path
import asyncpg

from app.ids import idempotency_key
from app.logging import log
from app.metrics import JOBS_STARTED, JOBS_COMPLETED, JOB_DURATION

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)
DSN = "postgresql://user:pass@localhost:5432/db"

COLUMNS = ("id", "order_id", "customer_id", "event_type", "status", "amount",
           "currency", "country", "payment_method", "product_sku",
           "quantity", "created_at", "metadata")

async def run_export(ctx, filters: dict):
    key = idempotency_key(filters)
    out = EXPORT_DIR / f"{key}.csv"
    JOBS_STARTED.labels(status_filter=filters.get("status") or "any").inc()
    start = time.perf_counter()

    # --- IDEMPOTENCY GUARD ---
    if out.exists():
        log.info("export.skip_existing", key=key, path=str(out))
        JOBS_COMPLETED.labels(outcome="skipped").inc()
        return {"key": key, "path": str(out), "skipped": True}

    # Write to a temp file first; rename on success → no half-written outputs.
    tmp = out.with_suffix(".csv.partial")

    where, args = [], []
    for k in ("status", "country", "customer_id"):
        v = filters.get(k)
        if v is not None:
            args.append(v)
            where.append(f"{k} = ${len(args)}")
    sql = f"SELECT {', '.join(COLUMNS)} FROM order_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at, id"

    rows_written = 0
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            with tmp.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                async for row in conn.cursor(sql, *args, prefetch=10_000):
                    w.writerow(row)
                    rows_written += 1
        tmp.rename(out)  # atomic on POSIX → retries never see a partial file
    except Exception as e:
        log.exception("export.failed", key=key, error=str(e))
        JOBS_COMPLETED.labels(outcome="failed").inc()
        if tmp.exists():
            tmp.unlink()
        raise
    finally:
        await conn.close()
        JOB_DURATION.observe(time.perf_counter() - start)

    log.info("export.done", key=key, rows=rows_written, path=str(out))
    JOBS_COMPLETED.labels(outcome="ok").inc()
    return {"key": key, "path": str(out), "rows": rows_written}
```

Three idempotency mechanisms layered together:

1. **Deterministic filename** from `idempotency_key(filters)` — same inputs map to same file.
2. **Existence check** — short-circuit if a previous run completed.
3. **Temp file + atomic rename** — a crash mid-write leaves no partial output to fool the existence check.

---

## Step 8 — API (HTTP only — Rule #7)

```python
# app/main.py
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pathlib import Path
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

from app.ids import idempotency_key
from app.logging import log

REDIS = RedisSettings(host="localhost", port=6379)
EXPORT_DIR = Path("exports")

app = FastAPI(title="Project 4 — Production jobs")

class ExportRequest(BaseModel):
    status: str | None = None
    country: str | None = None
    customer_id: int | None = None

@app.on_event("startup")
async def startup():
    app.state.redis = await create_pool(REDIS)

@app.post("/export")
async def start_export(req: ExportRequest):
    filters = req.model_dump()
    key = idempotency_key(filters)
    path = EXPORT_DIR / f"{key}.csv"
    if path.exists():
        log.info("export.cache_hit", key=key)
        return {"key": key, "status": "done", "cached": True}
    await app.state.redis.enqueue_job("run_export", filters, _job_id=key)
    return {"key": key, "status": "queued"}

@app.get("/export/{key}")
async def export_status(key: str):
    path = EXPORT_DIR / f"{key}.csv"
    if path.exists():
        return {"key": key, "status": "done", "size": path.stat().st_size}
    job = await app.state.redis.job(key)
    info = await job.info()
    if info is None:
        raise HTTPException(404, "unknown key")
    return {"key": key, "status": info.status}

@app.get("/export/{key}/file")
async def download(key: str):
    path = EXPORT_DIR / f"{key}.csv"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="text/csv", filename=f"{key}.csv")

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Notice the API process **never** opens a Postgres connection. It only talks to Redis. That is Rule #7 in code.

---

## Step 9 — Worker settings

```python
# app/worker.py
from arq.connections import RedisSettings
from app.jobs import run_export

class WorkerSettings:
    redis_settings = RedisSettings(host="localhost", port=6379)
    functions = [run_export]
    max_jobs = 4
    job_timeout = 1800
    keep_result = 3600
    max_tries = 5            # retries — safe because the job is idempotent
```

`max_tries = 5` is meaningful *only* because the job is idempotent. Without the guards in Step 7, retries would corrupt outputs.

---

## Step 10 — Run API and worker as separate processes

```bash
# Terminal A — API only (no CPU/file work)
uv run uvicorn app.main:app --port 8004 --workers 4

# Terminal B — Worker pool (no HTTP)
uv run arq app.worker.WorkerSettings
```

Two distinct process groups, two distinct scaling axes. That is Rule #7 at the deployment level.

---

## Step 11 — Verify each guarantee

**Idempotency:**

```bash
curl -X POST localhost:8004/export -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"key":"abc123…","status":"queued"}

# Wait for done, then submit the SAME filters:
curl -X POST localhost:8004/export -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"key":"abc123…","status":"done","cached":true}  ← second call did no work
```

**Observability — logs:**

```bash
# In worker terminal — you'll see JSON lines like:
# {"event":"export.done","key":"abc123…","rows":48217,"timestamp":"..."}
```

**Observability — metrics:**

```bash
curl localhost:8004/metrics | grep export_
# export_jobs_started_total{status_filter="paid"} 2.0
# export_jobs_completed_total{outcome="ok"} 1.0
# export_jobs_completed_total{outcome="skipped"} 1.0
# export_job_duration_seconds_bucket{le="5.0"} 1.0
```

**Retry safety:** kill the worker mid-export (`Ctrl+C` while it's writing). The `.partial` file is removed, and on next worker start Arq retries the job — it completes cleanly because the final file never existed yet.

---

## What this project proves

- ✅ Same filters → same key → same file. Retries are free.
- ✅ Atomic rename guarantees no partial outputs survive a crash.
- ✅ API and worker scale independently — Rule #7 honored at process boundary.
- ✅ Structured logs + Prometheus metrics make the job system observable.
- ✅ This is the "production-grade" terminus the article points to. Anything past this is domain-specific (per-tenant quotas, deadlines, priority lanes, dead-letter queues).
