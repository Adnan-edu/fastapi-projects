# 02 — Queue + Worker Export (Arq + Redis)

> **Pattern:** Dedicated worker architecture — submit job, poll status, download result
> **File:** `02_queue_worker_export.md` (formerly `project_2.md`)

**Source rules:** Option 2 (lines 157–207) of `backgroundjobs_async_parallel_processing_part_2.md`.

**Goal:** Move heavy work out of the request path. The API only **accepts** jobs and reports status; a separate worker process **performs** them.

Pattern from the article (line 167):

```
FastAPI → Queue → Worker → Storage → Client
```

We implement this with **Redis** (queue) + **Arq** (async worker runtime that matches FastAPI's asyncio model). Celery works too; Arq keeps the stack uniformly async and small.

---

## Dataset context

We use `/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils`:

- 1,000,000 rows of `order_events` already in Postgres
- The job we run: **export a filtered slice to CSV** (e.g., "all `paid` events in `US`")
- Filtering uses the indexes documented in `order_events_data_overview.md`:
  - `ix_order_events_created_at_id` for ordered scans
  - `ix_order_events_status` and `ix_order_events_customer_id` for predicates

A 1M-row table with a "status = X AND country = Y" filter can easily yield 100k+ rows. Doing that inline would block a `uvicorn` worker for many seconds — the exact case the article warns about.

---

## What you will build

```
POST /export {filters}     ──►  enqueue job_id in Redis  ──► return {job_id, queued}
GET  /export/{job_id}      ──►  read Arq job state       ──► {queued|in_progress|done|failed}
GET  /export/{job_id}/file ──►  stream the produced CSV from disk

Worker process (separate):
  pulls job_id ─► streams rows from Postgres in chunks ─► writes /exports/{job_id}.csv
```

---

## Step 1 — Virtual environment with `uv`

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects
mkdir -p project_2_worker_queue && cd project_2_worker_queue

uv init --python 3.12
uv add fastapi 'uvicorn[standard]' sqlalchemy asyncpg arq redis pydantic-settings
```

---

## Step 2 — Start Redis

```bash
docker run -d --name redis-arq -p 6379:6379 redis:7-alpine
```

---

## Step 3 — Verify the data, ingest only if needed

The Postgres data lives in a **Docker volume** and survives container restarts. Always check first — re-ingesting 1M rows when they are already loaded is wasted CPU and disk.

### 3a. Make sure the shared check script exists

Use the same `utils/check_ingested.py` from Project 1, Step 2a. If you haven't created it yet, do so now (one copy serves all four projects).

The script exits:
- `0` — `order_events` has all 1,000,000 rows → **skip ingest**
- `1` — table missing, empty, or partial → ingest (the loader is resumable)
- `2` — DB connection failed

### 3b. Run check, ingest only on non-zero exit

```bash
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"
export CSV_PATH="/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/data/order_events_1m.csv"

uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py \
  && echo "data ready — skipping ingest" \
  || uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/ingest_order_events.py
```

Project 2's export job streams from `order_events` — it relies on the `ix_order_events_created_at_id`, `ix_order_events_status`, and `ix_order_events_customer_id` indexes that the schema and the resumable loader put in place.

---

## Step 4 — Layout

```
project_2_worker_queue/
├── pyproject.toml
├── exports/                  # output CSVs (job_id.csv)
└── app/
    ├── main.py               # FastAPI: submit / status / download
    ├── worker.py             # Arq worker entrypoint
    ├── jobs.py               # the actual export function
    └── db.py
```

---

## Step 5 — Submission and status endpoints (article lines 174–199)

```python
# app/main.py
import uuid
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

REDIS = RedisSettings(host="localhost", port=6379)
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Project 2 — Queue + Worker")

class ExportRequest(BaseModel):
    status: str | None = None
    country: str | None = None
    customer_id: int | None = None

@app.on_event("startup")
async def startup():
    app.state.redis = await create_pool(REDIS)

@app.post("/export")
async def start_export(req: ExportRequest):
    job_id = str(uuid.uuid4())
    await app.state.redis.enqueue_job(
        "run_export", job_id, req.model_dump(), _job_id=job_id
    )
    return {"job_id": job_id, "status": "queued"}

@app.get("/export/{job_id}")
async def export_status(job_id: str):
    job = await app.state.redis.job(job_id)
    info = await job.info()
    if info is None:
        # Arq removes finished metadata after a TTL; fall back to file presence.
        path = EXPORT_DIR / f"{job_id}.csv"
        if path.exists():
            return {"job_id": job_id, "status": "done", "size": path.stat().st_size}
        raise HTTPException(404, "unknown job")
    return {"job_id": job_id, "status": info.status, "enqueue_time": info.enqueue_time}

@app.get("/export/{job_id}/file")
async def export_file(job_id: str):
    path = EXPORT_DIR / f"{job_id}.csv"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}.csv")
```

---

## Step 6 — The job (runs in the worker, NOT the API process)

```python
# app/jobs.py
import csv
from pathlib import Path
import asyncpg

EXPORT_DIR = Path("exports")
DSN = "postgresql://user:pass@localhost:5432/db"
CHUNK = 10_000

COLUMNS = ("id", "order_id", "customer_id", "event_type", "status", "amount",
           "currency", "country", "payment_method", "product_sku",
           "quantity", "created_at", "metadata")

async def run_export(ctx, job_id: str, filters: dict):
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

    out = EXPORT_DIR / f"{job_id}.csv"
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            with out.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                # Server-side cursor — does NOT load all rows in memory.
                async for row in conn.cursor(sql, *args, prefetch=CHUNK):
                    w.writerow(row)
    finally:
        await conn.close()
    return {"job_id": job_id, "rows_path": str(out)}
```

Two things worth noting:

1. `conn.cursor(...)` streams from Postgres in `prefetch`-sized chunks — bounded memory regardless of result size.
2. The `ORDER BY created_at, id` uses `ix_order_events_created_at_id` from `utils/order_events_schema.sql`.

---

## Step 7 — Worker settings

```python
# app/worker.py
from arq.connections import RedisSettings
from app.jobs import run_export

class WorkerSettings:
    redis_settings = RedisSettings(host="localhost", port=6379)
    functions = [run_export]
    max_jobs = 4         # concurrent jobs per worker process
    job_timeout = 1800   # 30 min cap for big exports
```

---

## Step 8 — Run both processes

Two **separate** terminals (this is Rule #7 from the article — never share the pool):

```bash
# Terminal A — API only
uv run uvicorn app.main:app --port 8002

# Terminal B — Worker only
uv run arq app.worker.WorkerSettings
```

---

## Step 9 — Try it

```bash
# Submit
curl -X POST localhost:8002/export \
  -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"job_id":"<uuid>","status":"queued"}

# Poll
curl localhost:8002/export/<uuid>
# → {"status":"in_progress"}  ... then  {"status":"complete"}

# Download
curl -OJ localhost:8002/export/<uuid>/file
```

---

## What this project proves

- ✅ API returns in milliseconds even for an export over hundreds of thousands of rows.
- ✅ API and worker are isolated — a stuck export does not block list endpoints.
- ✅ Streaming the query keeps worker memory flat.
- ✅ Polling lets the client wait without holding an HTTP connection open.
- ⚠️ Still single-threaded inside the worker — if the export becomes CPU-bound (Parquet, compression), graduate to Project 3.
