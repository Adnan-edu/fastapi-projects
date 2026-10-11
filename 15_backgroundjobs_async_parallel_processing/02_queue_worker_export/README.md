# Project 2 — Queue + Worker Export (FastAPI + Arq + Redis + Postgres)

> Move **heavy work out of the request path**: the API only **accepts**
> export jobs and reports status; a separate **Arq worker** process
> streams rows from Postgres to CSV.

This is the second project in the
`15_backgroundjobs_async_parallel_processing` series. Where
[Project 1](../01_bg_tasks_audit_logging/) used FastAPI
`BackgroundTasks` for tiny post-response I/O, **Project 2** demonstrates
the next escalation: a dedicated worker reachable via a Redis queue,
suitable for exports that take **seconds-to-minutes** and touch
hundreds of thousands of rows.

---

## Table of contents

1. [What this project proves](#what-this-project-proves)
2. [Architecture](#architecture)
3. [Request lifecycle](#request-lifecycle)
4. [Repo layout](#repo-layout)
5. [Prerequisites](#prerequisites)
6. [Setup](#setup)
7. [Run the API and the worker](#run-the-api-and-the-worker)
8. [Exercise the endpoints](#exercise-the-endpoints)
9. [Run the tests](#run-the-tests)
10. [Configuration](#configuration)
11. [When NOT to use this pattern](#when-not-to-use-this-pattern)

---

## What this project proves

- ✅ `POST /export` returns in **milliseconds** even for an export over hundreds of thousands of rows — the API process never touches Postgres.
- ✅ API and worker are **isolated processes**: a stuck export does not block list endpoints (Rule #7 from the source article — never share the connection pool).
- ✅ The worker uses an **asyncpg server-side cursor**: memory stays flat regardless of result size.
- ✅ The client **polls** instead of holding an HTTP connection open for the full duration.
- ✅ Even after Arq drops job metadata, `GET /export/{id}` falls back to **file presence on disk** so a stale `job_id` from yesterday still resolves.
- ⚠️ Single-threaded inside one worker process. CPU-bound exports (Parquet, compression) graduate to [Project 3](../03_multiprocessing_parquet_export/).

---

## Architecture

```
                              ┌──────────────────────────────────────────────┐
                              │                   Client                     │
                              │            (curl / browser / app)            │
                              └──────────────┬──────────────────────┬────────┘
                                             │ POST /export         │ GET /export/{id}[/file]
                                             ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                Uvicorn process — FastAPI (app/main.py)                       │
│                                                                              │
│   POST /export                                                               │
│      └─► uuid4() → job_id                                                    │
│      └─► await app.state.redis.enqueue_job("run_export", job_id, filters,    │
│                                            _job_id=job_id)                   │
│      └─► return {"job_id": …, "status": "queued"}   (milliseconds)           │
│                                                                              │
│   GET /export/{job_id}                                                       │
│      └─► arq.jobs.Job(job_id, redis).info()                                  │
│      └─► fallback to exports/{job_id}.csv if Arq forgot                      │
│                                                                              │
│   GET /export/{job_id}/file                                                  │
│      └─► FileResponse(exports/{job_id}.csv)                                  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ ENQUEUE / FETCH STATUS  (Redis list)
                                       ▼
                          ┌────────────────────────────┐
                          │      Redis  (Docker)       │
                          │      arq:queue list        │
                          │      arq:job:<id> hash     │
                          └─────────────┬──────────────┘
                                        │ BLPOP arq:queue
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│             Arq worker process  (app/worker.py → app/jobs.py)                │
│                                                                              │
│   run_export(ctx, job_id, filters):                                          │
│       sql, args = build_export_sql(filters)         # whitelist + ORDER BY   │
│       conn = await asyncpg.connect(DSN)                                      │
│       async with conn.transaction():                                         │
│           cur = conn.cursor(sql, *args, prefetch=10_000)   # server-side     │
│           async for row in cur:                                              │
│               csv.writer(...).writerow(row)         # bounded memory         │
│       write to exports/{job_id}.csv                                          │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ SELECT … ORDER BY created_at, id
                                       ▼
                       ┌─────────────────────────────────────┐
                       │       PostgreSQL  (Docker)          │
                       │   Table: order_events (~1M rows)    │
                       │   Indexes:                          │
                       │     ix_order_events_created_at_id   │
                       │     ix_order_events_status          │
                       │     ix_order_events_customer_id     │
                       └─────────────────────────────────────┘
```

---

## Request lifecycle

1. **Client →** `POST /export {"status":"paid","country":"US"}`
2. **API →** generates `job_id` (UUID v4), pushes `("run_export", job_id, filters)` onto Redis, returns `{job_id, status: "queued"}` immediately.
3. **Worker →** `BLPOP`s the queue, opens an asyncpg connection, runs the WHERE-filtered `SELECT` with a server-side cursor (`prefetch=10000`), writes rows to `exports/{job_id}.csv`, marks the job `complete`.
4. **Client polls** `GET /export/{job_id}` until it reads `status: "complete"`.
5. **Client downloads** `GET /export/{job_id}/file` — `FileResponse` streams the CSV.

If steps 1–3 happen on Monday and the client returns on Wednesday, Arq may have GC'd the job hash. The status endpoint then falls back to checking whether `exports/{job_id}.csv` is on disk and answers `done` if so — `404` otherwise.

---

## Repo layout

```
02_queue_worker_export/
├── README.md                    ← you are here
├── 02_queue_worker_export.md    ← the source rules from the article
├── pyproject.toml               ← uv-managed dependencies
├── pytest.ini                   ← asyncio_mode = auto
├── .gitignore
├── exports/                     ← output CSVs (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py                  ← FastAPI: submit / status / download
│   ├── jobs.py                  ← build_export_sql, write_csv, run_export
│   └── worker.py                ← Arq WorkerSettings entry point
└── tests/
    ├── __init__.py
    ├── conftest.py              ← FakeRedisPool, FakeJob, TestClient fixtures
    ├── test_build_sql.py        ← unit: SQL/arg builder
    ├── test_write_csv.py        ← unit: CSV writer
    ├── test_submit_endpoint.py  ← POST /export behaviour
    └── test_status_and_download.py
                                 ← GET /export/{id} and /file behaviour
```

---

## Prerequisites

- macOS / Linux with Docker
- Python **3.12** (the project pins this via `.python-version`)
- [uv](https://docs.astral.sh/uv/) ≥ 0.4
- A Postgres instance with the **1M-row `order_events` table** loaded
  via `../../utils/ingest_order_events.py` against the schema in
  `../../utils/order_events_schema.sql`.

---

## Setup

```bash
cd 02_queue_worker_export

# 1. Dependencies (installed into .venv via uv)
uv sync

# 2. Redis (queue + job state)
docker run -d --name redis-arq -p 6379:6379 redis:7-alpine

# 3. Postgres — only if you don't already have `order_events` loaded.
#    The shared utils/ingester is resumable; safe to re-run.
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"
export CSV_PATH="$(pwd)/../../utils/data/order_events_1m.csv"
uv run python ../../utils/check_ingested.py \
  && echo "data ready" \
  || uv run python ../../utils/ingest_order_events.py
```

---

## Run the API and the worker

Two **separate** terminals. Sharing the connection pool between the API
and the worker is exactly the failure mode the queue/worker pattern
exists to prevent.

```bash
# Terminal A — FastAPI
export ASYNCPG_DSN="postgresql://user:pass@localhost:5432/db"
export REDIS_HOST=localhost REDIS_PORT=6379
uv run uvicorn app.main:app --port 8002

# Terminal B — Arq worker
export ASYNCPG_DSN="postgresql://user:pass@localhost:5432/db"
export REDIS_HOST=localhost REDIS_PORT=6379
uv run arq app.worker.WorkerSettings
```

---

## Exercise the endpoints

```bash
# Submit
curl -X POST localhost:8002/export \
  -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"job_id":"<uuid>","status":"queued"}

# Poll
curl localhost:8002/export/<uuid>
# → {"job_id":"<uuid>","status":"in_progress","enqueue_time": …}
# … then
# → {"job_id":"<uuid>","status":"complete","enqueue_time": …, "size": 1795909}

# Download
curl -OJ localhost:8002/export/<uuid>/file
```

A real submit/poll/download against the 1M-row table on this machine
returned a 1.7 MB CSV with **16,692 lines** for the
`status='paid' AND country='US'` slice — start to finish in under a
second of worker time.

---

## Run the tests

```bash
# Whole suite
uv run pytest

# A single file
uv run pytest tests/test_build_sql.py

# A single test
uv run pytest tests/test_status_and_download.py::test_status_falls_back_to_file_when_arq_forgot
```

The suite contains **15 tests across 4 files** and runs in ~0.1 s — it
never touches Redis or Postgres because:

- The Arq Redis pool is replaced by a `FakeRedisPool` that records
  `enqueue_job` calls and serves scripted `job(...)` lookups.
- The `EXPORT_DIR` is monkey-patched to a `tmp_path`.
- The SQL builder and the CSV writer are pure functions, tested with
  literals.

What each file covers:

| File | What it pins down |
|---|---|
| `test_build_sql.py` | WHERE clause uses positional `$N`, `None` filters are skipped, unknown keys can't reach SQL, `ORDER BY created_at, id` is always present. |
| `test_write_csv.py` | Header row is always written; `None` becomes empty cell, not the string `"None"`. |
| `test_submit_endpoint.py` | UUID job_id, `status: "queued"`, correct `enqueue_job` arguments, empty body allowed. |
| `test_status_and_download.py` | Live status → `in_progress`; missing Arq metadata + file present → `done`; missing both → `404`; download serves CSV, missing file → `404`. |

---

## Configuration

Read at process start via environment variables:

| Variable | Default | Used by |
|---|---|---|
| `ASYNCPG_DSN` | `postgresql://cursor:cursor@localhost:5432/cursor_pagination` | worker (`app/jobs.py`) |
| `REDIS_HOST` | `localhost` | API + worker |
| `REDIS_PORT` | `6379` | API + worker |
| `EXPORT_DIR` | `exports` | API (file fallback + download) and worker (output path) |

The defaults are tuned for the local Docker setup documented above.

---

## When NOT to use this pattern

- The job runs in **sub-100 ms** and is pure I/O after the response — use Project 1 (`BackgroundTasks`).
- The job is **CPU-bound** (Parquet encode, gzip, image transcode) — a single Arq worker still GIL-blocks; graduate to Project 3 (`ProcessPoolExecutor`).
- You need **strict exactly-once** semantics or cross-job idempotency keys — graduate to Project 4.

Otherwise — bounded-memory database export, web hook fan-out, report
generation — this is the pattern.
