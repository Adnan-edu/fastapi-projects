# Project 1 — FastAPI `BackgroundTasks` Audit Logging

> Demonstrates FastAPI's built-in `BackgroundTasks` for **lightweight, post-response I/O** —
> append an audit-log line *after* the HTTP response is sent, without blocking the client.

This is the first project in the
`15_backgroundjobs_async_parallel_processing` series. It establishes the
baseline pattern that later projects (Celery, RQ, `asyncio.gather`,
`ProcessPoolExecutor`, …) will compare against.

---

## Table of contents

1. [What this project proves](#what-this-project-proves)
2. [Architecture](#architecture)
3. [Request lifecycle](#request-lifecycle)
4. [Repo layout](#repo-layout)
5. [Prerequisites](#prerequisites)
6. [Setup](#setup)
7. [Run the API](#run-the-api)
8. [Exercise the endpoint](#exercise-the-endpoint)
9. [Run the tests](#run-the-tests)
10. [When NOT to use this pattern](#when-not-to-use-this-pattern)

---

## What this project proves

- ✅ `BackgroundTasks` runs **after** the response is flushed — latency stays low.
- ✅ Safe for single-append log writes, single emails, small notifications.
- ❌ **Not** for CPU-heavy work or large I/O — it shares the uvicorn event loop and will starve other requests. That failure mode is exactly what Projects 2+ in this series address.

---

## Architecture

```
                             ┌────────────────────────────────────────────────┐
                             │                    Client                      │
                             │              (curl / browser / app)            │
                             └───────────────────────┬────────────────────────┘
                                                     │ GET /orders?...
                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Uvicorn (single process)                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                       FastAPI application                              │  │
│  │                                                                        │  │
│  │   app/main.py  ── @app.get("/orders")                                  │  │
│  │       │                                                                │  │
│  │       │ 1. Depends(get_session)                                        │  │
│  │       ▼                                                                │  │
│  │   app/db.py  ── async SQLAlchemy session ───┐                          │  │
│  │       │                                     │                          │  │
│  │       │ 2. SELECT ... FROM order_events     │                          │  │
│  │       │                                     │                          │  │
│  │       │ 3. Build JSON response              │                          │  │
│  │       │                                     │                          │  │
│  │       │ 4. background_tasks.add_task(       │                          │  │
│  │       │        write_audit_log, ...)        │                          │  │
│  │       │                                     │                          │  │
│  │       ▼                                     │                          │  │
│  │   ── Response sent to client ─────────────  │  ◄── client unblocked    │  │
│  │       │                                     │                          │  │
│  │       │ 5. AFTER response flushed:          │                          │  │
│  │       ▼                                     │                          │  │
│  │   app/audit.py ── write_audit_log() ──► audit.log (append)             │  │
│  └─────────────────────────────────────────────┼──────────────────────────┘  │
│                                                │                             │
└────────────────────────────────────────────────┼─────────────────────────────┘
                                                 │
                                                 ▼
                              ┌────────────────────────────────────┐
                              │       PostgreSQL  (Docker)         │
                              │   Table: order_events (~1M rows)   │
                              │   Indexes: (created_at, id),       │
                              │            customer_id, status     │
                              └────────────────────────────────────┘
```

Key invariants:

- The audit write is enqueued **before** `return`, but executed **after** the response is sent — FastAPI walks the `BackgroundTasks` queue once the response body is on the wire.
- Everything runs in the same Python process and the same event loop. There is **no broker, no worker, no queue**. That is the whole point of `BackgroundTasks` — and also its hard limit.

---

## Request lifecycle

```
Time ──►

t0 ─ Client sends   GET /orders?status=paid&limit=10
t1 ─ FastAPI resolves Depends(get_session) → opens async session
t2 ─ SELECT … executes against Postgres
t3 ─ Rows serialized to JSON
t4 ─ background_tasks.add_task(write_audit_log, …)   ◄── scheduled, NOT yet run
t5 ─ HTTP 200 response flushed to client             ◄── client is now unblocked
t6 ─ FastAPI drains BackgroundTasks queue
t7 ─ write_audit_log() opens audit.log, appends 1 line, closes
t8 ─ Session closed by `async with`
```

`t5 → t7` is the entire reason this pattern exists: the audit cost is paid off the critical path.

---

## Repo layout

```
01_bg_tasks_audit_logging/
├── README.md                         # this file
├── 01_bg_tasks_audit_logging.md      # design notes / source rules
├── pyproject.toml                    # uv-managed dependencies
├── pytest.ini                        # test config
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app + /orders endpoint
│   ├── db.py                         # async engine + get_session dependency
│   ├── models.py                     # OrderEvent ORM mapping
│   └── audit.py                      # write_audit_log() — the BG task
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # FakeSession, TestClient fixture
│   ├── test_audit_writer.py          # 3 unit tests
│   ├── test_background_task.py       # 2 integration tests
│   └── test_orders_endpoint.py       # 4 endpoint tests
└── audit.log                         # created at runtime (gitignored in spirit)
```

Shared, external to this project (one level up):

```
../../utils/
├── data/order_events_1m.csv          # 1,000,000 rows
├── order_events_schema.sql           # table + indexes
├── ingest_order_events.py            # resumable asyncpg COPY loader
└── check_ingested.py                 # exit 0 if data is ready
```

---

## Prerequisites

| Tool       | Version           | Why                              |
|------------|-------------------|----------------------------------|
| Python     | 3.12+             | `Mapped[...]` typing syntax      |
| `uv`       | 0.4+              | Dependency + virtualenv manager  |
| PostgreSQL | 14+ (Docker is ok)| Stores `order_events`            |
| `curl`     | any               | Hitting the endpoint manually    |

The Postgres data lives in a **Docker volume**, so once loaded it persists across `docker compose down/up`. Don't re-ingest blindly — run the check first.

---

## Setup

### 1. Install dependencies

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/15_backgroundjobs_async_parallel_processing/01_bg_tasks_audit_logging

uv sync
```

`uv sync` installs the locked deps declared in `pyproject.toml`:

- **runtime:** `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `asyncpg`
- **dev:** `pytest`, `pytest-asyncio`, `httpx`

### 2. Verify the dataset (and ingest only if needed)

The ingest script is resumable — but checking first is faster than re-COPY'ing 1M rows.

```bash
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"

uv run python ../../utils/check_ingested.py \
  && echo "data ready — skipping ingest" \
  || uv run python ../../utils/ingest_order_events.py \
       --csv ../../utils/data/order_events_1m.csv
```

Outcomes from `check_ingested.py`:

| stdout                              | exit | action                         |
|-------------------------------------|------|--------------------------------|
| `status=ready rows=1,000,000`       | `0`  | skip ingest                    |
| `status=missing_table`              | `1`  | run ingest                     |
| `status=empty rows=0`               | `1`  | run ingest                     |
| `status=partial rows=…`             | `1`  | run ingest (resumes from MAX(id)) |

---

## Run the API

`db.py` reads `DATABASE_URL` at import time and expects the **asyncpg** driver
(`postgresql+asyncpg://…`), not the plain `postgresql://…` form used by the
ingest script.

```bash
DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db" \
uv run uvicorn app.main:app --reload --port 8001
```

Once up:

- API: `http://localhost:8001/orders`
- OpenAPI UI: `http://localhost:8001/docs`

---

## Exercise the endpoint

In one terminal, tail the audit log:

```bash
tail -f audit.log
```

In another, hit the endpoint:

```bash
# Basic call
curl "http://localhost:8001/orders?limit=5"

# Filtered call
curl "http://localhost:8001/orders?status=paid&customer_id=42&limit=10"
```

You should see the HTTP response come back **first**, then a single audit
line land in `audit.log`. Sample:

```
2026-05-28T12:34:56.789012+00:00	user=42	path=/orders	query={'customer_id': 42, 'status': 'paid', 'limit': 10}
```

### Query parameters

| Param         | Type | Default | Constraint | Notes                          |
|---------------|------|---------|------------|--------------------------------|
| `customer_id` | int  | —       | optional   | filters by customer            |
| `status`      | str  | —       | optional   | e.g. `paid`, `refunded`        |
| `limit`       | int  | `50`    | `≤ 500`    | violation returns HTTP 422     |

---

## Run the tests

The test suite stubs the DB session and redirects `audit.log` to a
`tmp_path`, so **no Postgres is required** to run it.

```bash
# Full suite
uv run pytest -v

# A single file
uv run pytest tests/test_background_task.py -v

# A single test
uv run pytest tests/test_audit_writer.py::test_write_audit_log_timestamp_is_iso_utc -v

# Just collect (no execution)
uv run pytest --collect-only -q
```

Expected: **9 passed in ~0.3s**.

Coverage at a glance:

| File                          | What it locks down                                          |
|-------------------------------|-------------------------------------------------------------|
| `test_audit_writer.py`        | single-line append, no clobber, ISO-8601 UTC timestamp      |
| `test_background_task.py`     | `add_task` fires after response; multiple requests append   |
| `test_orders_endpoint.py`     | payload shape, `limit ≤ 500`, query type coercion (422s)    |

---

## When NOT to use this pattern

`BackgroundTasks` runs **in the same process and event loop** as the API
handlers. Use it only when the task is:

- **Fast** (sub-second, ideally sub-100ms).
- **Bounded memory** — no huge buffers, no streaming large files.
- **Not CPU-bound** — no compression, no rendering, no parsing big payloads.
- **Tolerant of loss** — if uvicorn is `SIGKILL`'d between flush and task, the work disappears.

If any of those don't hold:

| Need                                          | Use instead                              |
|-----------------------------------------------|------------------------------------------|
| Heavy CPU (PDF, ML inference, aggregation)    | `ProcessPoolExecutor` / Celery worker    |
| Durable, retryable, observable jobs           | Celery / RQ / Arq with Redis or RabbitMQ |
| Fan-out concurrent I/O within one request     | `asyncio.gather`                         |
| Cross-service pipelines, scheduled jobs       | Celery beat / Temporal / Airflow         |

Later projects in this series implement each of those — Project 1 is the
control case to measure them against.

---

## License / scope

Educational. Part of the `medium/fastapi_projects` study notes — not a
deployable service. The audit format is intentionally trivial (`tab-separated key=value`); in production use structured JSON and ship to a log aggregator.
