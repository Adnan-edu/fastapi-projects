# FastAPI Data Pipeline

A composable streaming data pipeline exposed as a FastAPI endpoint. Reads from
PostgreSQL via keyset pagination, runs the rows through pluggable
filter/transform/sink stages, and streams the result to the client as NDJSON
(or CSV) — all in **bounded memory**, no matter how many rows are involved.

This project is the sibling of `13_fastapi_streaming` and shares the same
database, the same `order_events` table, and the same Docker container
(`stream_pg`). It does **not** re-ingest data; it simply offers a different
shape of API on top of the same dataset.

---

## 1. What this project demonstrates

A pipeline is not a clever name for "a streaming endpoint." It's a composition
primitive. This codebase turns the conceptual flow

```
Database → Filter → Chunk → Transform → Stream → Client
```

into real Python `Stage` objects that compose, where each stage:

- has **bounded memory** — never holds more than one chunk at a time;
- is **independently optimizable** — swap the source, swap the sink, retune
  the chunk size, without touching the rest;
- **fails without cascading** — an error in one stage closes that stage
  cleanly and surfaces to the client; upstream stages don't deadlock or leak
  DB connections.

The three invariants above are not aspirations — they're tests
(`tests/test_invariants.py`). If they pass, the abstraction earns its keep.

### How it differs from `13_fastapi_streaming`

`13_fastapi_streaming` hard-codes four endpoint shapes (`export.csv`,
`report.ndjson`, `feed.ndjson`, etc.). Each is a hand-rolled streaming
handler. This project composes those shapes from stages — so adding a fifth
shape is a stage, not a new router file.

### When NOT to use this

For a one-off export, the hand-rolled streaming endpoint in
`13_fastapi_streaming` is simpler and equally correct. The pipeline
abstraction earns its keep when you have **three or more** consumers (HTTP
endpoint, batch job, Kafka producer, …) that share stages.

---

## 2. Project layout

```
14_fastapi_pipeline/
  .env                       # DB URL, port, pipeline knobs
  .gitignore
  pyproject.toml             # deps + pytest config
  pipevenv/                  # uv-managed virtualenv (gitignored)
  fastapi_pipeline.md        # original spec / build instructions

  app/                       # FastAPI HTTP layer
    __init__.py
    config.py                # Settings (DATABASE_URL, PIPELINE_CHUNK_SIZE, …)
    db.py                    # async engine + async_sessionmaker
    models.py                # OrderEvent ORM model (shared with 13_…)
    main.py                  # FastAPI app + lifespan
    routers/
      __init__.py
      health.py              # /healthz, /readyz
      pipeline.py            # /pipeline/run.ndjson — the demo endpoint

  pipeline/                  # The pipeline library (HTTP-independent)
    __init__.py
    core.py                  # Stage, Source Protocols + Pipeline composer
    errors.py                # StageError + @stage_errors decorator
    stages/
      __init__.py
      source.py              # DbKeysetSource
      filter.py              # PredicateFilter
      chunk.py               # Rechunk
      transform.py           # Projection, Enrich
      sink.py                # NdjsonSink, CsvSink

  tests/
    __init__.py
    test_invariants.py       # bounded memory, swap-a-stage, fail-without-cascade
    test_endpoint.py         # smoke test via httpx ASGITransport
```

---

## 3. From initial stage to final stage — a walkthrough

### 3.1 Scaffolding (`pyproject.toml`, `.env`)

The project was initialized with `uv init --no-readme`, a dedicated
`pipevenv` virtualenv, and these dependencies:

- **Runtime:** `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`,
  `asyncpg`, `pydantic`, `pydantic-settings`
- **Dev:** `pytest`, `pytest-asyncio`, `httpx`, `ruff`

`pytest-asyncio` is configured in `[tool.pytest.ini_options]` with
`asyncio_mode = "auto"`, so async test functions don't need a marker.

`.env` holds connection details and pipeline knobs. The app port is `8002`
(deliberately different from `13_fastapi_streaming` on `8001`, so both can
run side by side).

### 3.2 The pipeline core (`pipeline/core.py`, `pipeline/errors.py`)

Three primitives:

- **`Stage`** (Protocol) — consumes an `AsyncIterator` and produces another.
  Every stage is an async generator; backpressure flows automatically because
  `yield` suspends until the downstream consumer pulls.
- **`Source`** (Protocol) — like a Stage but has no upstream; produces items
  from somewhere external (a DB, an HTTP feed, a file).
- **`Pipeline`** — holds a `Source` and a tuple of `Stage`s. `Pipeline.run()`
  is itself an async generator that wraps the composed stream in
  `contextlib.aclosing(...)` so a downstream raise/break triggers `aclose()`
  on every upstream generator, running their `finally:` blocks **in order**.

**Why `aclosing` matters.** Python does not automatically close a paused
upstream generator when a downstream generator raises. The upstream is left
suspended at its `yield`, and only the eventual garbage collector calls
`__del__`/`aclose()` — too late to be useful, and on the wrong event loop.
Without `aclosing`, the "fail-without-cascading" invariant would silently
leak DB sessions. With it, the invariant holds and is testable.

**Errors.** `pipeline/errors.py` defines `StageError(stage_name, cause)` and
a `@stage_errors` decorator. Every stage's `__call__` is wrapped with it: any
non-`StageError` raised inside the body is re-raised as
`StageError(self.name, e)`, while existing `StageError`s are passed through
unchanged so the original failing stage's name survives downstream re-wrapping.
This removes the repeated `try / except StageError: raise / except Exception:`
boilerplate from every stage body.

### 3.3 The stages (`pipeline/stages/*.py`)

| File           | Class(es)                  | Role                                                                                  |
|----------------|----------------------------|---------------------------------------------------------------------------------------|
| `source.py`    | `DbKeysetSource`           | Keyset-paginated DB source. One short `AsyncSession` per chunk, not a long cursor.    |
| `filter.py`    | `PredicateFilter`          | Apply a `Callable[[T], bool]`; skip non-matches. Escape hatch for "can't do in SQL".  |
| `chunk.py`     | `Rechunk`                  | Regroup a stream into `list[T]` of size `N`. Bounded-memory rebatching.               |
| `transform.py` | `Projection`, `Enrich`     | Per-item transforms → dict. `Projection` keeps named fields; `Enrich` merges a fn().  |
| `sink.py`      | `NdjsonSink`, `CsvSink`    | Terminal stages: serialize items to `bytes`. `csv.writer` handles per-row quoting.    |

**`DbKeysetSource` is the most important one.** It loops with
`WHERE id > :last_id ORDER BY id LIMIT :chunk_size`, opens a fresh
`AsyncSession` per chunk, drains the rows into a list, **closes the session**,
and only then yields rows downstream. This is what makes the
"fail-without-cascading" guarantee real: when a downstream stage raises, the
source is paused between chunks with zero open DB sessions.

### 3.4 The FastAPI layer (`app/`)

- **`app/config.py`** — `pydantic_settings.BaseSettings`. Reads `.env`.
  Exposes `database_url`, `pipeline_chunk_size`, `pipeline_max_rows`, pool
  sizing.
- **`app/db.py`** — `init_engine()` / `dispose_engine()` driven by the FastAPI
  lifespan. Exposes both `get_session()` (a Depends-style dependency for
  health checks) and `get_sessionmaker()` (so the pipeline can open its own
  per-chunk sessions). Engine and sessionmaker are module-level singletons,
  initialized on startup.
- **`app/models.py`** — `OrderEvent` ORM model. Identical schema to
  `13_fastapi_streaming`. The `metadata` column is mapped as `metadata_`
  because `metadata` is a reserved attribute on SQLAlchemy `DeclarativeBase`.
- **`app/main.py`** — wires lifespan, mounts the `health` and `pipeline`
  routers, exposes a `/` index for discoverability.
- **`app/routers/health.py`** — `/healthz` (liveness) and `/readyz` (DB
  readiness via `SELECT 1`).
- **`app/routers/pipeline.py`** — the demo endpoint. Builds a `Pipeline` from
  query parameters and returns a `StreamingResponse` of `application/x-ndjson`.
  Wraps `pipeline.run()` in `_safe_stream()` which converts a mid-stream
  `StageError` into a trailing `{"type":"error","stage":…,"detail":…}` NDJSON
  line instead of letting Starlette emit a truncated body.

### 3.5 The tests (`tests/`)

`tests/test_invariants.py` — three tests, one per invariant:

1. **`test_bounded_memory[100]` and `[10000]`** — feed 200 000 synthetic rows
   through the pipeline and assert `tracemalloc` peak stays under 50 MB.
   Parameterized so we see that the assertion holds whether chunks are small
   or large — the point is that peak does **not** scale with row count.
2. **`test_swap_a_stage_ndjson_vs_csv`** — runs the same 100-row source
   through two pipelines, one ending in `NdjsonSink` and one in `CsvSink`.
   Asserts identical row count, different byte format. Proves stages are
   independently swappable.
3. **`test_fail_without_cascading`** — inserts a predicate that raises on the
   50th row. Asserts the error surfaces as `StageError` with the right
   `stage_name`, that the source's `finally:` ran (`open_count == 0`,
   `closed_cleanly is True`), and that no `RuntimeError: Task was destroyed
   but it is pending` warnings were emitted.

`tests/test_endpoint.py` — smoke tests using `httpx.AsyncClient` with
`ASGITransport(app)`:

- `GET /pipeline/run.ndjson?limit=5` returns exactly 5 NDJSON lines with
  strictly increasing `id`s.
- `GET /pipeline/run.ndjson?status=paid&limit=10` returns rows whose `status`
  is `paid` — proving the SQL `where_clauses` push-down works.

### 3.6 The demo endpoint contract

```
GET /pipeline/run.ndjson
  ?after_id=0          # keyset cursor; resume after this id
  &status=paid         # optional; becomes a SQL WHERE on OrderEvent.status
  &min_amount=100      # optional; becomes a Python-side PredicateFilter
  &chunk_size=1000     # overrides PIPELINE_CHUNK_SIZE
  &limit=10000         # optional cap on rows pulled from the DB
```

Pipeline shape built per request:

```
DbKeysetSource
  → [PredicateFilter(min_amount)]   # only if min_amount given
  → Projection(id, order_id, amount, status, country, created_at)
  → NdjsonSink
```

The `status` filter is pushed into SQL via `where_clauses` (so non-matching
rows never leave the DB). `min_amount` is a Python predicate — kept as the
"escape hatch" example. Note: `limit` caps **source rows**, not output rows;
if the predicate rejects most of them you may see fewer lines back.

---

## 4. Architectural decisions worth knowing

- **One task, not many.** Every stage runs in the same asyncio task. We do
  **not** wrap stages in `asyncio.create_task` with a bounded `asyncio.Queue`.
  The simpler single-task model gives us automatic backpressure (because
  `yield` suspends), simpler error propagation, and cheap cleanup via
  `aclosing`. The cost is no parallelism between stages — but for a streaming
  endpoint, the bottleneck is almost always the database or the network, not
  the per-item Python work.
- **Short transactions, not server-side cursors.** `DbKeysetSource` opens a
  fresh `AsyncSession` per chunk. This trades a small per-chunk overhead for
  the property that a downstream raise can never leave a session open.
- **Errors are values, sort of.** Inside the pipeline they're exceptions
  (`StageError`). At the HTTP boundary they become a structured NDJSON
  trailing line. The HTTP consumer never sees a 500 mid-stream — those would
  be indistinguishable from a network truncation.

---

## 5. Commands — verify, run, test

> All commands assume the working directory is `14_fastapi_pipeline/` and
> `pipevenv` is the active virtualenv:
>
> ```bash
> source pipevenv/bin/activate
> ```

### 5.1 Verify prerequisites

```bash
# 1. Docker container from 13_fastapi_streaming is up and healthy
docker ps --filter name=stream_pg

# 2. The order_events table is populated (any row count > 0 is fine)
docker exec -it stream_pg psql -U stream -d stream_pagination \
  -c "SELECT count(*) FROM order_events;"

# 3. uv is installed
uv --version

# 4. The app loads (imports, model registration, settings parse cleanly)
python -c "from app.main import app; print('app loaded:', app.title)"
```

### 5.2 Run the test suite

```bash
# Full suite — should print "6 passed"
uv run --active pytest -v

# Just the invariants (offline; no DB needed)
uv run --active pytest -v tests/test_invariants.py

# Just the endpoint smoke tests (requires stream_pg up)
uv run --active pytest -v tests/test_endpoint.py
```

### 5.3 Run the API server

```bash
# Foreground (Ctrl-C to stop)
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

# Health checks
curl -s http://localhost:8002/healthz
curl -s http://localhost:8002/readyz
```

### 5.4 Exercise the demo endpoint

```bash
# First 5 rows, default chunk size
curl -sN 'http://localhost:8002/pipeline/run.ndjson?limit=5'

# Resume after id 100, SQL-filter to paid orders, larger chunks
curl -sN 'http://localhost:8002/pipeline/run.ndjson?after_id=100&status=paid&chunk_size=10000&limit=3'

# Python-side predicate (min_amount). Use a larger source limit so the
# predicate has rows to keep — `limit` caps source rows, not output rows.
curl -sN 'http://localhost:8002/pipeline/run.ndjson?min_amount=500&limit=200' | head -5

# OpenAPI / Swagger UI
open http://localhost:8002/docs
```

### 5.5 Lint (optional)

```bash
uv run --active ruff check .
uv run --active ruff format --check .
```
