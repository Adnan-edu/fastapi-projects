# Project 4 — Idempotent & Observable Jobs

> Production-grade FastAPI + Arq background job system. Layered on top of
> [Project 2](../02_queue_worker_export/) with three new guarantees:
> **idempotency**, **process isolation** (API ⟂ worker pools), and
> **observability** (structured logs + Prometheus metrics).

Source spec: [`04_idempotent_observable_jobs.md`](./04_idempotent_observable_jobs.md)

---

## End-to-end architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                Client (curl / SDK)                           │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  FastAPI process  (uvicorn :8004, --workers N)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  POST /export        → idempotency_key(filters) → enqueue_job       │    │
│  │  GET  /export/{key}  → status from disk OR redis                    │    │
│  │  GET  /export/{key}/file → FileResponse                             │    │
│  │  GET  /metrics       → MultiProcessCollector aggregate              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│   - No DB connection.  No CPU work.  Talks only to Redis + filesystem.       │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │  arq enqueue / status
                                 ▼
                ┌──────────────────────────────────┐
                │   Redis (queue + job metadata)   │
                │   docker: redis-arq :6379        │
                └────────────────┬─────────────────┘
                                 │  arq dequeue (separate process group)
                ┌────────────────┴──────────────────┐
                ▼                                   ▼
┌─────────────────────────────┐       ┌─────────────────────────────┐
│  Arq worker pool A          │       │  Arq worker pool B          │
│  app.worker.WorkerSettings  │       │  app.worker.WorkerSettings  │
│  max_jobs=4  max_tries=5    │       │  max_jobs=4  max_tries=5    │
│                             │       │                             │
│  run_export(filters):       │       │  run_export(filters):       │
│   1. key = sha256(filters)  │       │   …                         │
│   2. if exports/key.csv     │       │                             │
│      exists → return        │       │                             │
│   3. write to key.csv.      │       │                             │
│      partial                │       │                             │
│   4. atomic rename          │       │                             │
└─────────────┬───────────────┘       └─────────────┬───────────────┘
              │ asyncpg cursor (prefetch=10k)       │
              ▼                                     ▼
        ┌──────────────────────────────────────────────────┐
        │   Postgres (cursor_pg :5432)                     │
        │   order_events  (1,000,000 rows)                 │
        └──────────────────────────────────────────────────┘

              │ writes                              │ writes
              ▼                                     ▼
        ┌──────────────────────────────────────────────────┐
        │   ./exports/<key>.csv   (shared volume)          │
        │   ./PROM_MULTIPROC_DIR/ (shared metrics files)   │
        └──────────────────────────────────────────────────┘
```

### Three guarantees in code

| Guarantee | Where it lives |
|---|---|
| **Idempotency** | `app/ids.py` (deterministic key) + `app/jobs.py` (existence check + atomic rename) |
| **API ⟂ worker separation** (Rule #7) | `app/main.py` opens **zero** Postgres connections; `app/worker.py` is its own process |
| **Observability** | `app/log_setup.py` (structlog JSON) + `app/metrics.py` (Prometheus multiprocess) |

---

## Layout

```
04_idempotent_observable_jobs/
├── app/
│   ├── ids.py          # idempotency_key(filters) -> 16-char hex
│   ├── log_setup.py    # structlog JSON logger
│   ├── metrics.py      # Counter / Histogram / Gauge (multiprocess-safe)
│   ├── jobs.py         # run_export — idempotent, atomic
│   ├── main.py         # FastAPI — HTTP only (Rule #7)
│   └── worker.py       # Arq WorkerSettings (max_tries=5)
├── tests/
│   ├── conftest.py             # boots API + worker subprocesses
│   ├── test_idempotency_key.py # 4 unit tests
│   ├── test_sql_builder.py     # 3 unit tests
│   └── test_api_e2e.py         # 7 e2e tests against live stack
├── exports/                    # generated CSVs (gitignored)
├── pyproject.toml
├── pytest.ini
└── README.md
```

---

## Prerequisites

| Service | How |
|---|---|
| Redis 7 on `localhost:6379` | `docker run -d --name redis-arq -p 6379:6379 redis:7-alpine` |
| Postgres 16 on `localhost:5432` with `cursor_pagination.order_events` (1M rows) | shared `cursor_pg` container — see [utils/](../../utils/) and Project 1 ingest |
| Python 3.12 + `uv` | `brew install uv` |

DSN used by default: `postgresql://cursor:cursor@localhost:5432/cursor_pagination`
(override via `ASYNCPG_DSN`).

---

## Setup

```bash
cd 04_idempotent_observable_jobs/
uv sync                       # installs from pyproject.toml
```

Verify the 1M rows are present (idempotent — re-runs are safe):

```bash
uv run python ../../utils/check_ingested.py \
  && echo "data ready" \
  || uv run python ../../utils/ingest_order_events.py
```

---

## Run (two terminals)

```bash
# Terminal A — API process (no CPU, no DB)
uv run uvicorn app.main:app --port 8004 --workers 4

# Terminal B — Arq worker pool (no HTTP)
uv run arq app.worker.WorkerSettings
```

For real Prometheus aggregation across the two processes, both need a
shared `PROMETHEUS_MULTIPROC_DIR`:

```bash
export PROMETHEUS_MULTIPROC_DIR=$(pwd)/prom_multiproc
mkdir -p "$PROMETHEUS_MULTIPROC_DIR" && rm -f "$PROMETHEUS_MULTIPROC_DIR"/*
# then start API + worker in the same shell session (or export it
# inside each terminal before launching).
```

> Without the env var, `/metrics` still works — it just shows the API
> process's own registry, which has no worker counters. The tests set
> the variable automatically.

---

## Smoke test

```bash
# 1) First submission — queued
curl -s -X POST localhost:8004/export \
  -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"key":"…","status":"queued"}

# 2) Wait a second, then submit the same filters — cache hit, no work done
curl -s -X POST localhost:8004/export \
  -H 'content-type: application/json' \
  -d '{"status":"paid","country":"US"}'
# → {"key":"…","status":"done","cached":true}

# 3) Inspect job state
curl -s localhost:8004/export/<key>
# → {"key":"…","status":"done","size":123456}

# 4) Download the CSV
curl -s localhost:8004/export/<key>/file -o out.csv && head -3 out.csv

# 5) Metrics
curl -s localhost:8004/metrics | grep ^export_
# export_jobs_started_total{status_filter="paid"} 1.0
# export_jobs_completed_total{outcome="ok"} 1.0
# export_job_duration_seconds_count 1.0
# export_queue_depth 0.0
```

---

## Run the test suite

```bash
docker exec redis-arq redis-cli flushdb       # tests refuse to run against a non-empty queue
uv run pytest                                  # 14 tests, ~6s
```

Coverage (14 tests):

| # | Test | What it proves |
|---|------|----------------|
| 1 | `test_idempotency_key_stable` | Same filters → same key (deterministic) |
| 2 | `test_idempotency_key_order_invariant` | Key order in dict doesn't matter |
| 3 | `test_idempotency_key_drops_none` | `None` values are normalized out |
| 4 | `test_idempotency_key_distinct_for_distinct_filters` | Different filters → different keys |
| 5 | `test_filters_are_whitelisted` | SQL injection vector closed at builder |
| 6 | `test_no_filters_means_no_where` | Empty filters → no WHERE clause |
| 7 | `test_multi_filter_positional_args` | Positional args track FILTER_COLUMNS order |
| 8 | `test_post_export_enqueues` | POST returns queued + stable key |
| 9 | `test_post_export_cached_hit` | Second identical POST is cache hit |
| 10 | `test_status_endpoint_progresses` | Status endpoint reaches `done` |
| 11 | `test_download_file_endpoint` | CSV is downloadable with header + body |
| 12 | `test_atomic_rename_no_partial` | No `.partial` files survive success |
| 13 | `test_metrics_endpoint_exposes_counters` | `/metrics` aggregates worker counters via multiprocess |
| 14 | `test_unknown_key_returns_404` | Bogus key → 404 on status + file endpoints |

---

## What this project proves

- ✅ Same filters → same key → same file. Retries are free.
- ✅ `.partial` + atomic rename guarantees no half-written outputs survive a crash.
- ✅ API and worker scale independently — Rule #7 honored at process boundary.
- ✅ Structured JSON logs + Prometheus metrics (cross-process via multiprocess mode) make the system observable.
- ✅ `max_tries=5` is safe only because the job is idempotent — Rule #8 in code.
