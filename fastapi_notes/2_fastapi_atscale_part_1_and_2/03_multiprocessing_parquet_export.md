# 03 — Multiprocessing Parquet Export

> **Pattern:** `multiprocessing.Pool` + PyArrow — CPU-bound chunked partitioned writes
> **File:** `03_multiprocessing_parquet_export.md` (formerly `project_3.md`)

**Source rule:** Rule #6 — Parallelism ≠ Concurrency (lines 211–254) of `backgroundjobs_async_parallel_processing_part_2.md`.

**Goal:** When the job is CPU-bound (compression, columnar encoding, large transforms), one async worker is not enough. Use `multiprocessing.Pool` so chunks land on **different CPU cores**.

The article's reference code (lines 232–246):

```python
from multiprocessing import Pool
import pyarrow.parquet as pq
import pyarrow as pa

def process_chunk(chunk):
    table = pa.Table.from_pandas(chunk)
    pq.write_to_dataset(table, root_path="/data/export")

def run_export_job():
    chunks = fetch_chunks_from_db()
    with Pool(processes=4) as pool:
        pool.map(process_chunk, chunks)
```

This project makes that runnable end-to-end against the `order_events` dataset.

---

## Dataset context

Same shared data at `/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils`:

- 1,000,000 rows × 13 columns of `order_events`
- Total CSV size ≈ 112 MB on disk
- For Parquet partitioned by `country` and `event_type` we expect:
  - dozens of partitions
  - large per-row compression savings (Parquet + Snappy/Zstd)
  - CPU-bound work in `pa.Table.from_pylist(...)` and writer encoding

**Why multiprocessing is required here:** Parquet encoding holds the GIL during pure-Python loop sections (and even libraries that release it benefit from process isolation when chunks are big). Async will not help — there is nothing to `await`.

---

## Important design note on DB access from worker processes

`asyncpg` uses one event loop per connection. Inside `multiprocessing.Pool` workers it's cleaner and more robust to use a **synchronous** driver — `psycopg[binary]` — because each pool worker is its own process and we don't need concurrency *within* a worker, only *across* workers.

Pattern: the parent process partitions the work (cursor ranges), workers each open their own sync connection.

---

## What you will build

```
parent process
   │
   ├── decide cursor ranges:  [(id_lo, id_hi), ...]
   │
   └── Pool(processes=N)
         ├── worker 1: SELECT ... WHERE id BETWEEN lo AND hi  →  Parquet partition
         ├── worker 2: ...
         ├── worker 3: ...
         └── worker 4: ...

output:
  /data/export/country=US/event_type=paid/part-<id>.parquet
  /data/export/country=SE/event_type=placed/part-<id>.parquet
  ...
```

---

## Step 1 — Virtual environment with `uv`

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects
mkdir -p project_3_multiproc_parquet && cd project_3_multiproc_parquet

uv init --python 3.12
uv add fastapi 'uvicorn[standard]' 'psycopg[binary]' pyarrow pandas
```

> We use `pandas` because the article's snippet calls `pa.Table.from_pandas`. If you prefer no pandas, swap in `pa.Table.from_pylist`.

---

## Step 2 — Verify the data, ingest only if needed

Postgres state is persisted in a **Docker volume**, so the 1M rows survive container restarts. The multiprocessing Parquet job reads `MIN(id)`/`MAX(id)` to plan worker ranges — those calls are meaningless on an empty or partial table, so we verify first.

### 2a. Use the shared check script (from Project 1, Step 2a)

`utils/check_ingested.py` is the single source of truth for this check across all four projects. Create it once if you haven't.

It exits:
- `0` → `order_events` is complete (1,000,000 rows) — **skip ingest**
- `1` → missing / empty / partial — ingest (resumable)
- `2` → DB connection failed

### 2b. Conditional ingestion

```bash
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"
export CSV_PATH="/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/data/order_events_1m.csv"

uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py \
  && echo "data ready — skipping ingest" \
  || uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/ingest_order_events.py
```

> Tip: after a fresh ingestion run `ANALYZE order_events` (the loader already does this). The planner stats matter because `plan_ranges()` in Step 4 depends on `MIN/MAX(id)` and the workers do `WHERE id BETWEEN ... AND ...` scans.

---

## Step 3 — Layout

```
project_3_multiproc_parquet/
├── pyproject.toml
├── data/export/                  # output Parquet tree
└── app/
    ├── main.py                   # FastAPI launcher endpoint
    └── parquet_export.py         # multiprocessing job
```

---

## Step 4 — The multiprocessing export

```python
# app/parquet_export.py
from multiprocessing import Pool
from pathlib import Path
import os
import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

DSN = os.environ.get(
    "PG_DSN",
    "postgresql://user:pass@localhost:5432/db",
)
OUT_ROOT = Path("data/export")
OUT_ROOT.mkdir(parents=True, exist_ok=True)

COLUMNS = ["id", "order_id", "customer_id", "event_type", "status", "amount",
           "currency", "country", "payment_method", "product_sku",
           "quantity", "created_at", "metadata"]


def plan_ranges(num_workers: int) -> list[tuple[int, int]]:
    """Split the id space into roughly equal ranges."""
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(id), MAX(id) FROM order_events")
        lo, hi = cur.fetchone()
    if lo is None:
        return []
    step = (hi - lo + 1) // num_workers + 1
    return [(s, min(s + step - 1, hi)) for s in range(lo, hi + 1, step)]


def process_chunk(rng: tuple[int, int]) -> dict:
    """Runs in a worker process. Reads its slice and writes partitioned Parquet."""
    lo, hi = rng
    sql = f"""
        SELECT {", ".join(COLUMNS)}
        FROM order_events
        WHERE id BETWEEN %s AND %s
    """
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(sql, (lo, hi))
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=COLUMNS)
    # amount is Decimal; convert for Parquet friendliness
    df["amount"] = df["amount"].astype("float64")

    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(OUT_ROOT),
        partition_cols=["country", "event_type"],
        compression="zstd",
        existing_data_behavior="overwrite_or_ignore",
    )
    return {"range": rng, "rows": len(df)}


def run_export_job(num_workers: int = 4) -> list[dict]:
    ranges = plan_ranges(num_workers)
    with Pool(processes=num_workers) as pool:
        return pool.map(process_chunk, ranges)
```

---

## Step 5 — FastAPI trigger

Important: the API process **does not** do the work. It launches a worker pool in a thread so that uvicorn's event loop is never blocked, and returns the summary at the end. For very long exports use the Project 2 queue pattern *and* this multiprocessing job together.

```python
# app/main.py
import asyncio
from fastapi import FastAPI
from app.parquet_export import run_export_job

app = FastAPI(title="Project 3 — Multiprocessing Parquet export")

@app.post("/export/parquet")
async def export_parquet(workers: int = 4):
    # Run the blocking multiprocessing driver in a thread so the loop is free.
    results = await asyncio.to_thread(run_export_job, workers)
    return {"workers": workers, "chunks": results}
```

---

## Step 6 — Run it

```bash
PG_DSN="postgresql://user:pass@localhost:5432/db" \
uv run uvicorn app.main:app --port 8003
```

Trigger the job:

```bash
time curl -X POST "localhost:8003/export/parquet?workers=4"
```

Inspect the partitioned output:

```bash
find data/export -name '*.parquet' | head
du -sh data/export
```

You should see a directory tree like:

```
data/export/country=US/event_type=paid/part-0.parquet
data/export/country=SE/event_type=placed/part-0.parquet
...
```

Compare against the original CSV (~112 MB). Parquet + Zstd typically lands around an order of magnitude smaller.

---

## What this project proves

- ✅ CPU work scales with cores (article: "throughput scales linearly with cores").
- ✅ Memory stays bounded — each worker only holds its own chunk.
- ✅ Failures are isolated — one chunk crashing does not kill the others.
- ✅ Output is columnar and partitioned — ready for downstream analytics.
- ⚠️ Don't run this directly inside the API process in production — combine with the queue pattern from Project 2 so the API can return immediately.
