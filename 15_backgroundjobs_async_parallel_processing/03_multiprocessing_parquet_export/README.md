# Project 3 — Multiprocessing Parquet Export

> **Pattern:** `multiprocessing.Pool` + PyArrow — CPU-bound chunked partitioned writes.
> A FastAPI endpoint fans out work to N OS processes, each one reads its own slice of
> `order_events` from PostgreSQL and writes a partitioned, Zstd-compressed Parquet
> dataset to disk.

This is the runnable companion to `03_multiprocessing_parquet_export.md`, demonstrating
**Rule #6 — Parallelism ≠ Concurrency** against the shared 1,000,000-row `order_events`
dataset.

---

## 1. Architecture (box diagram)

```
                        ┌────────────────────────────────────────────┐
                        │                Client (curl)               │
                        └───────────────┬────────────────────────────┘
                                        │  POST /export/parquet?workers=4
                                        ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │                       FastAPI / Uvicorn (port 8003)                │
   │                                                                    │
   │   app/main.py                                                      │
   │   ─────────────────────────────                                    │
   │   async def export_parquet(workers):                               │
   │       results = await asyncio.to_thread(                           │
   │           run_export_job, workers)   ◀── event loop stays free     │
   │       return {"workers": ..., "total_rows": ..., "chunks": ...}    │
   └───────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼ (worker thread launches Pool)
   ┌────────────────────────────────────────────────────────────────────┐
   │                  app/parquet_export.py — Parent process            │
   │                                                                    │
   │   plan_ranges(N)  ── SELECT MIN(id), MAX(id) FROM order_events     │
   │        │                                                           │
   │        └─▶ [(1, 250001), (250002, 500002), (500003, 750003), ...]  │
   │                                                                    │
   │              multiprocessing.Pool(processes=N).map(process_chunk)  │
   └───────────┬───────────┬───────────┬───────────┬────────────────────┘
               │           │           │           │
               ▼           ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker 4 │ ◀ OS processes
        │  (own    │ │          │ │          │ │          │   each pinned
        │  psycopg │ │          │ │          │ │          │   to its own
        │  conn)   │ │          │ │          │ │          │   CPU core
        └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │            │
             │   SELECT … WHERE id BETWEEN %s AND %s│
             ▼            ▼            ▼            ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │                   PostgreSQL 16  (docker: cursor_pg)               │
   │                   table: order_events  (1,000,000 rows)            │
   └────────────────────────────────────────────────────────────────────┘
             │            │            │            │
             │ pa.Table.from_pandas + pq.write_to_dataset (CPU-bound)   │
             ▼            ▼            ▼            ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │                           data/export/                             │
   │   country=US/event_type=paid/<uuid>-0.parquet                      │
   │   country=SE/event_type=placed/<uuid>-0.parquet                    │
   │   country=DE/event_type=out_for_delivery/<uuid>-0.parquet          │
   │   …                                                                │
   │   (15 countries × ~6 event_types ≈ 90 partition directories)       │
   │   Compression: Zstd  •  ~36 MB total vs ~112 MB CSV (~3× smaller)  │
   └────────────────────────────────────────────────────────────────────┘
```

### Why multiprocessing — not async

Parquet encoding is **CPU-bound**: PyArrow does heavy work in `pa.Table.from_pandas`
and the writer's columnar encoding. A single asyncio task cannot speed this up
because there is nothing to `await`. With `multiprocessing.Pool`, each worker runs
in its own process and on its own CPU core, sidestepping the GIL entirely.

### Why a sync DB driver inside workers

`asyncpg` uses one event loop per connection. Inside `Pool` workers it is cleaner
and more robust to use a synchronous driver (`psycopg[binary]`): each worker is its
own process, and we only need parallelism **across** workers, not concurrency
**within** them.

---

## 2. Project layout

```
03_multiprocessing_parquet_export/
├── 03_multiprocessing_parquet_export.md   # source article
├── README.md                              # this file
├── pyproject.toml                         # uv project (workspace member)
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── parquet_export.py                  # plan_ranges + process_chunk + run_export_job
│   └── main.py                            # FastAPI launcher (/export/parquet)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                        # DB-availability gate + tmp_out_root fixture
│   └── test_parquet_export.py             # 7 test cases
└── data/
    └── export/                            # partitioned Parquet output (gitignored)
```

---

## 3. Prerequisites

| Component       | Version / Notes                                                  |
| --------------- | ---------------------------------------------------------------- |
| Python          | 3.12                                                             |
| uv              | any recent                                                       |
| PostgreSQL      | 16, running on `localhost:5432`, db `cursor_pagination`          |
| `order_events`  | already loaded with 1,000,000 rows (ids 1 … 1,000,000)           |

The PostgreSQL container from Project 12 (`cursor_pg`) is the source of data:

```bash
docker ps --filter name=cursor_pg
# 0.0.0.0:5432->5432/tcp   postgres:16-alpine
```

If the table is empty, ingest it from the shared CSV (one-time):

```bash
export ASYNCPG_URL="postgresql://cursor:cursor@localhost:5432/cursor_pagination"
export CSV_PATH="/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/data/order_events_1m.csv"

uv run python ../../utils/ingest_order_events.py
```

---

## 4. Install & run

```bash
# from this directory
cd 15_backgroundjobs_async_parallel_processing/03_multiprocessing_parquet_export

# install deps (handled by uv workspace at /Users/.../python)
uv sync

# point at the DB
export PG_DSN="postgresql://cursor:cursor@localhost:5432/cursor_pagination"

# launch the API
uv run uvicorn app.main:app --port 8003
```

Trigger the export:

```bash
# health check
curl -s http://localhost:8003/health

# full export with 4 worker processes
time curl -s -X POST "http://localhost:8003/export/parquet?workers=4" | jq .
```

Sample response:

```json
{
  "workers": 4,
  "chunks": [
    {"range": [1,      250001], "rows": 250001, "seconds": 2.243},
    {"range": [250002, 500002], "rows": 250001, "seconds": 2.356},
    {"range": [500003, 750003], "rows": 250001, "seconds": 2.366},
    {"range": [750004, 1000000],"rows": 249997, "seconds": 2.365}
  ],
  "total_rows": 1000000,
  "out_root": "data/export"
}
```

Inspect the partitioned output:

```bash
find data/export -name '*.parquet' | head
find data/export -type d -name 'country=*'    | wc -l   # 15 countries
find data/export -type d -name 'event_type=*' | wc -l   # ~90 partitions
du -sh data/export                                      # ~36 MB
```

---

## 5. Tests

The tests gate themselves on DB availability — if `cursor_pg` is not running, the
whole module is skipped instead of failing.

Run the whole suite:

```bash
PG_DSN="postgresql://cursor:cursor@localhost:5432/cursor_pagination" \
  uv run pytest -v
```

Run a single test by name:

```bash
uv run pytest tests/test_parquet_export.py::test_plan_ranges_partitions_id_space -v
uv run pytest tests/test_parquet_export.py::test_process_chunk_writes_partitioned_parquet -v
uv run pytest tests/test_parquet_export.py::test_run_export_job_full_dataset -v
uv run pytest tests/test_parquet_export.py::test_api_endpoint_runs_job -v
```

### Test inventory

| # | Test                                              | What it proves                                                            |
| - | ------------------------------------------------- | ------------------------------------------------------------------------- |
| 1 | `test_plan_ranges_partitions_id_space`            | `plan_ranges(N)` produces N contiguous, non-overlapping ranges covering all ids |
| 2 | `test_plan_ranges_rejects_zero_workers`           | `plan_ranges(0)` raises `ValueError`                                      |
| 3 | `test_process_chunk_writes_partitioned_parquet`   | A single worker writes `country=/event_type=` directories                 |
| 4 | `test_process_chunk_schema_matches_columns`       | The resulting Parquet dataset's schema includes all 13 expected columns   |
| 5 | `test_run_export_job_full_dataset`                | End-to-end with 4 workers — exactly 1,000,000 rows land in the dataset    |
| 6 | `test_api_endpoint_runs_job`                      | `POST /export/parquet?workers=2` returns `total_rows == 1,000,000`        |
| 7 | `test_api_endpoint_rejects_invalid_workers`       | `workers=0` returns an error payload                                      |

Each test redirects `PARQUET_OUT_ROOT` to a per-test `tmp_path/export`, so they
never collide with each other or with `data/export`.

---

## 6. Environment variables

| Variable            | Default                                                          | Purpose                                       |
| ------------------- | ---------------------------------------------------------------- | --------------------------------------------- |
| `PG_DSN`            | `postgresql://cursor:cursor@localhost:5432/cursor_pagination`    | DSN used by parent and worker processes       |
| `PARQUET_OUT_ROOT`  | `data/export`                                                    | Root of the partitioned Parquet output tree   |

---

## 7. What this project proves

- ✅ CPU work scales with cores — 4 workers process 1M rows in ~3 s wall time.
- ✅ Memory stays bounded — each worker only holds its own slice.
- ✅ Failures are isolated — one worker crashing does not kill the others.
- ✅ Output is columnar and partitioned — directly usable by downstream analytics tools.
- ⚠️ In production, combine this with the queue pattern from Project 2 so the API can
  return immediately rather than waiting for the Pool to finish.
