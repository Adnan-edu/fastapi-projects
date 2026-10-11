# Build a FastAPI Data Pipeline — End-to-End Instructions

This document is a self-contained, step-by-step prompt for building a new
FastAPI project that exposes a **composable data pipeline** as a streaming
HTTP endpoint. It is a sibling to the `13_fastapi_streaming` project: same
PostgreSQL instance, same `order_events` table, no re-ingest required.

The goal is to turn the conceptual pipeline

$$\text{Database} \rightarrow \text{Filter} \rightarrow \text{Chunk} \rightarrow \text{Transform} \rightarrow \text{Stream} \rightarrow \text{Client}$$

into real Python `Stage` objects that compose, each of which:

* has **bounded memory** (never holds more than one chunk at a time),
* is **independently optimizable** (swap the source, swap the sink, retune the chunk size — without touching the rest),
* **fails without cascading** (an error in one stage closes that stage cleanly and surfaces to the client; upstream stages don't deadlock or leak DB connections).

---

## 0. Prerequisites

Before starting, verify the following are already true on the machine:

1. **Docker is running** and the `stream_pg` container from
   `13_fastapi_streaming/docker-compose.yml` is up:
   ```bash
   docker ps --filter name=stream_pg
   ```
   Expected: a `postgres:16-alpine` container in `healthy` state with port
   mapping `0.0.0.0:5433->5432/tcp`.

2. **Data is already ingested.** Do **not** run `scripts/ingest.py` again.
   Sanity-check the row count:
   ```bash
   docker exec -it stream_pg psql -U stream -d stream_pagination \
     -c "SELECT count(*) FROM order_events;"
   ```
   Expected: ~1,000,000 rows.

3. **`uv` is installed** (`uv --version`). If not, install from
   <https://docs.astral.sh/uv/>.

### Database connection details

| Field    | Value                  |
|----------|------------------------|
| Host     | `localhost`            |
| Port     | `5433`                 |
| User     | `stream`               |
| Password | `stream`               |
| DB name  | `stream_pagination`    |

SQLAlchemy URL: `postgresql+asyncpg://stream:stream@localhost:5433/stream_pagination`

### Dataset schema (`order_events`)

| Column          | Type           | Notes                                            |
|-----------------|----------------|--------------------------------------------------|
| `id`            | `BIGINT` PK    | Monotonic, used as the keyset cursor             |
| `order_id`      | `BIGINT`       |                                                  |
| `customer_id`   | `BIGINT`       | Indexed                                          |
| `event_type`    | `TEXT`         | `placed` / `paid` / `packed` / `shipped` / ...   |
| `status`        | `TEXT`         | Indexed: `pending` / `paid` / `fulfilled` / ...  |
| `amount`        | `NUMERIC(12,2)`|                                                  |
| `currency`      | `TEXT`         | `USD` / `EUR` / ...                              |
| `country`       | `TEXT`         | ISO-2                                            |
| `payment_method`| `TEXT`         | `card` / `paypal` / `apple_pay` / ...            |
| `product_sku`   | `TEXT`         |                                                  |
| `quantity`      | `INTEGER`      |                                                  |
| `created_at`    | `TIMESTAMP`    | Indexed jointly with `id`                        |
| `metadata`      | `TEXT` nullable| Semicolon-separated key=value pairs              |

Indexes already in place: `(created_at, id)`, `(customer_id)`, `(status)`.

---

## 1. Scaffold the project

Create a sibling directory next to `13_fastapi_streaming`:

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects
mkdir 14_data_pipeline
cd 14_data_pipeline
```

Initialize the project and a **dedicated** virtualenv (don't reuse
`streamvenv`):

```bash
uv init --no-readme
uv venv pipevenv
source pipevenv/bin/activate
```

Add dependencies:

```bash
uv add fastapi 'uvicorn[standard]' sqlalchemy[asyncio] asyncpg \
       pydantic pydantic-settings
uv add --dev pytest pytest-asyncio httpx ruff
```

Then install everything into the active venv:

```bash
uv sync --active
```

Create a `.env` file:

```env
DATABASE_URL=postgresql+asyncpg://stream:stream@localhost:5433/stream_pagination
APP_HOST=0.0.0.0
APP_PORT=8002
APP_LOG_LEVEL=info

PIPELINE_CHUNK_SIZE=1000
PIPELINE_MAX_ROWS=0

DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

> Port `8002` is deliberate — `13_fastapi_streaming` already uses `8001`. Both
> apps can run side-by-side.

---

## 2. Target layout

Build toward this structure:

```
14_data_pipeline/
  .env
  pyproject.toml
  uv.lock
  pipevenv/                    # uv-managed virtualenv (gitignored)
  app/
    __init__.py
    config.py                  # Settings (incl. PIPELINE_CHUNK_SIZE)
    db.py                      # Async engine + sessionmaker
    models.py                  # OrderEvent ORM model (copy from 13_fastapi_streaming)
    main.py                    # FastAPI app + lifespan
    routers/
      __init__.py
      health.py                # /healthz, /readyz
      pipeline.py              # /pipeline/run.ndjson — the demo endpoint
  pipeline/
    __init__.py
    core.py                    # Stage, Pipeline, types
    errors.py                  # StageError hierarchy
    stages/
      __init__.py
      source.py                # DbKeysetSource
      filter.py                # PredicateFilter
      chunk.py                 # Rechunk (regroup arbitrary streams into N-sized batches)
      transform.py             # Projection, Enrich
      sink.py                  # NdjsonSink, CsvSink
  tests/
    __init__.py
    test_invariants.py         # bounded memory, fail-without-cascading, swap-a-stage
    test_endpoint.py           # smoke test via httpx
```

---

## 3. Implement the pipeline core (`pipeline/core.py`)

Define three things:

### 3.1 Types

```python
from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

T_in = TypeVar("T_in")
T_out = TypeVar("T_out")

class Stage(Protocol[T_in, T_out]):
    """A stage consumes an async iterator and produces another.

    Stages MUST:
    - Be async generators (so backpressure flows automatically).
    - Yield items one at a time — never accumulate a list of all input.
    - Close any owned resources in a `finally:` block so a downstream
      exception can't leak a DB connection / file handle.
    """
    name: str
    async def __call__(self, upstream: AsyncIterator[T_in]) -> AsyncIterator[T_out]: ...
```

The first stage in a pipeline is a **Source** — it takes no upstream and
produces items from somewhere external:

```python
class Source(Protocol[T_out]):
    name: str
    async def __call__(self) -> AsyncIterator[T_out]: ...
```

### 3.2 Pipeline composition

```python
class Pipeline:
    def __init__(self, source: Source, *stages: Stage):
        self.source = source
        self.stages = stages

    async def run(self) -> AsyncIterator:
        stream = self.source()
        for stage in self.stages:
            stream = stage(stream)
        async for item in stream:
            yield item
```

Notes the implementer should keep in mind:

- **No `list()` anywhere.** If a stage needs to batch (e.g. `Rechunk`), it
  yields a `list[T]` *of bounded size* and immediately discards it.
- **Each stage runs in the same task.** This is intentional — backpressure
  is automatic because `yield` suspends until the consumer pulls. Don't
  wrap stages in `asyncio.create_task` unless you also add a bounded
  `asyncio.Queue` between them.
- **Errors propagate via exception, not sentinel.** A stage that fails
  raises `StageError(stage_name, cause)`; the response handler converts that
  into a trailing NDJSON `{"type": "error", ...}` line so the consumer
  observes the failure instead of silently truncating.

### 3.3 Errors (`pipeline/errors.py`)

```python
class StageError(Exception):
    def __init__(self, stage_name: str, cause: BaseException):
        super().__init__(f"stage '{stage_name}' failed: {cause!r}")
        self.stage_name = stage_name
        self.cause = cause
```

---

## 4. Implement the stages

### 4.1 `pipeline/stages/source.py` — `DbKeysetSource`

The DB source must use the **chunking pattern** (short transactions, keyset
pagination), not one long server-side cursor — that is what makes
"fail without cascading" testable.

Key requirements:

- Accepts an `async_sessionmaker[AsyncSession]` and a `chunk_size`.
- Loops with `WHERE id > :last_id ORDER BY id LIMIT :chunk_size`.
- Opens a fresh `AsyncSession` per chunk and closes it **before** yielding
  rows downstream.
- Stops when a chunk comes back smaller than `chunk_size`.
- Wraps any exception in `StageError("db_keyset_source", e)`.

Constructor signature:

```python
DbKeysetSource(
    sessionmaker,
    *,
    chunk_size: int,
    after_id: int = 0,
    where_clauses: list = None,  # extra SQLAlchemy WHERE expressions
)
```

### 4.2 `pipeline/stages/filter.py` — `PredicateFilter`

A trivial stage that applies an arbitrary `Callable[[T], bool]` and skips
non-matching items. Demonstrates that filters can also live in Python — but
in real use cases, push as much as possible into the SQL `where_clauses` on
the source. Keep this one as the "I couldn't express this in SQL" escape
hatch.

### 4.3 `pipeline/stages/chunk.py` — `Rechunk`

Regroups a stream of items into `list[T]` of size `N`, flushing a partial
batch at end-of-stream. Useful when a downstream stage wants batches even
though the source emits one row at a time (e.g. batched HTTP POSTs to a
warehouse, batched insert into another table).

Invariant: never holds more than `N` items in memory.

### 4.4 `pipeline/stages/transform.py` — `Projection`, `Enrich`

- `Projection(fields: Iterable[str])` — keep only the listed attributes,
  output a `dict`.
- `Enrich(fn: Callable[[T], dict])` — call an arbitrary function per item,
  merge the result into a dict. Useful for joining in static lookups,
  computing derived fields, etc.

### 4.5 `pipeline/stages/sink.py` — `NdjsonSink`, `CsvSink`

Sinks are the *last* stage. They convert items to `bytes` and yield them.
Keep them dumb — no buffering across items beyond what `csv.writer` needs
for a single line.

```python
class NdjsonSink:
    name = "ndjson_sink"
    async def __call__(self, upstream):
        async for item in upstream:
            yield (json.dumps(item, default=str) + "\n").encode("utf-8")
```

---

## 5. Wire up the FastAPI app

### 5.1 `app/config.py`

`pydantic_settings.BaseSettings` with `database_url`, `pipeline_chunk_size`,
`pipeline_max_rows`, pool sizes. Mirror the shape used in
`13_fastapi_streaming/app/config.py`.

### 5.2 `app/db.py`

`init_engine()`, `dispose_engine()`, `get_session()` dependency. Identical
shape to `13_fastapi_streaming/app/db.py`. Expose the `async_sessionmaker`
so the pipeline can open its own sessions per chunk (don't make
`get_session` the only path in).

### 5.3 `app/models.py`

Copy `OrderEvent` from `13_fastapi_streaming/app/models.py` verbatim. Same
table, same indexes, no migration needed.

### 5.4 `app/main.py`

Standard FastAPI app with a `lifespan` that calls `init_engine()` on
startup and `dispose_engine()` on shutdown. Mount the health router and the
pipeline router.

### 5.5 `app/routers/pipeline.py` — the demo endpoint

```
GET /pipeline/run.ndjson
  ?after_id=0
  &status=paid           # optional, becomes a SQL where_clause
  &min_amount=100        # optional, becomes a Python PredicateFilter
  &chunk_size=1000       # overrides PIPELINE_CHUNK_SIZE
  &limit=10000           # optional cap
```

The handler should:

1. Build the pipeline:
   ```python
   pipeline = Pipeline(
       DbKeysetSource(sessionmaker, chunk_size=..., after_id=..., where_clauses=...),
       PredicateFilter(lambda r: r.amount >= min_amount) if min_amount else identity,
       Projection(["id", "order_id", "amount", "status", "country", "created_at"]),
       NdjsonSink(),
   )
   ```
2. Wrap `pipeline.run()` in an async generator that:
   - Yields each `bytes` chunk.
   - On `StageError`, yields a final `{"type":"error","stage":...,"detail":...}`
     NDJSON line, then returns. **Do not raise** out of the generator —
     Starlette would 500 mid-stream and the consumer would see a truncated
     body with no error context.
3. Returns a `StreamingResponse` with `application/x-ndjson` and
   `X-Accel-Buffering: no`.

---

## 6. Tests — prove the three invariants

These tests are the point of the project. Without them, the framework is
just indirection.

### 6.1 `tests/test_invariants.py`

- **`test_bounded_memory`**: feed a synthetic 1M-row in-memory source into
  the pipeline; assert `tracemalloc` peak stays under `chunk_size * row_size
  * safety_factor`. Run the same assertion with `chunk_size=100` and
  `chunk_size=10_000` and check that peak memory scales linearly with chunk
  size — never with row count.
- **`test_swap_a_stage`**: build the same pipeline twice, once with
  `NdjsonSink` and once with `CsvSink`. Run both against a 100-row source.
  Assert: identical row count, different byte format. Proves stages are
  independently swappable.
- **`test_fail_without_cascading`**: insert a `Filter` stage that raises on
  the 50th item. Run the pipeline; assert:
  - The error is reported as a `StageError` with the right `stage_name`.
  - The DB source's last session is closed (use a fixture that tracks
    open sessions — assert count is zero after the generator exits).
  - No `RuntimeError: Task was destroyed but it is pending` warnings.

### 6.2 `tests/test_endpoint.py`

Spin up the app with `httpx.AsyncClient(transport=ASGITransport(app))`. Hit
`/pipeline/run.ndjson?limit=5` and assert:

- HTTP 200.
- `Content-Type: application/x-ndjson`.
- Exactly 5 NDJSON lines, each a valid JSON object containing `id`.
- The 5 `id`s are strictly increasing.

---

## 7. Run it

```bash
source pipevenv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

Try the endpoint:

```bash
# First 5 rows, default chunk size
curl -sN 'http://localhost:8002/pipeline/run.ndjson?limit=5'

# Resume after id 12345, filter to paid orders, larger chunks
curl -sN 'http://localhost:8002/pipeline/run.ndjson?after_id=12345&status=paid&chunk_size=10000'

# Apply a Python-side predicate (min_amount) — proves PredicateFilter works
curl -sN 'http://localhost:8002/pipeline/run.ndjson?min_amount=500&limit=10'
```

Run the test suite:

```bash
uv run --active pytest -v
```

---

## 8. README checklist

Once the project runs, write a `README.md` that covers:

- **What this project demonstrates** — pipeline as a composition primitive,
  not just a streaming endpoint.
- **The three invariants**, each linked to the test that enforces it.
- **How to swap a stage** — show the one-line change that turns NDJSON into
  CSV, or DB source into a file source.
- **How this differs from `13_fastapi_streaming`** — that project hard-codes
  the four endpoint shapes; this one composes them from stages, so adding
  a new shape is a stage, not a router file.
- **When not to use it** — for a one-off export, the hand-rolled streaming
  endpoint in `13_fastapi_streaming` is simpler and equally correct. The
  pipeline abstraction earns its keep when you have **three or more**
  consumers (HTTP endpoint, batch job, Kafka producer) that share stages.

---

## 9. Stretch goals (do not block on these)

- **`HttpSource`** — pull rows from another service's `/feed.ndjson`
  (e.g. `13_fastapi_streaming`'s feed endpoint), proving the pipeline
  doesn't care whether the source is local or remote.
- **`KafkaSink` stub** — yield to an in-memory queue instead of HTTP. Same
  pipeline, different terminal.
- **Per-stage metrics** — a `MeteredStage` wrapper that records throughput
  and p50/p99 latency per stage and exposes them at `/metrics`.
- **Backpressure visualization** — log a warning when a stage's `yield`
  blocks for more than `N` ms; this is the symptom of a slow consumer.
