# Large Responses Must Be Streamed

Companion to [`12_cursor_pagination`](../12_cursor_pagination). Same dataset,
same schema, different problem: instead of returning a page, the endpoints
here stream the whole result set without ever holding it in memory.

> Streaming flips the model:
> - You don't wait for all the data.
> - You don't hold everything in memory.
> - You send results as they're produced.
>
> Streaming is not an optimization; it's survival.

## The four use cases

| Endpoint                       | Purpose                                  | Format                 | DB shape                          |
|--------------------------------|------------------------------------------|------------------------|-----------------------------------|
| `GET /stream/export.csv`       | Export a subset of data                  | `text/csv`             | One server-side cursor            |
| `GET /stream/report.ndjson`    | Generate a report over millions of rows  | `application/x-ndjson` | One server-side cursor            |
| `GET /stream/feed.ndjson`      | Feed downstream systems                  | `application/x-ndjson` | One server-side cursor            |
| `GET /stream/chunked.ndjson`   | Stream events using many short tx chunks | `application/x-ndjson` | Many short keyset-paged SELECTs   |

The first three use the same primitive: an async generator that walks a
*single* server-side cursor in chunks (`STREAM_CHUNK_SIZE` rows per fetch) and
yields rows as they arrive — one DB transaction stays open for the whole
response. The fourth flips that around: it runs many short transactions
(`SELECT ... WHERE id > :last_id LIMIT N`), one chunk at a time, while still
streaming the response to the client. Memory in both shapes is bounded by the
chunk size, not the row count.

## Layout

```
app/
  config.py            # Settings (incl. STREAM_CHUNK_SIZE, STREAM_MAX_ROWS)
  db.py                # Async engine + get_session dependency
  models.py            # OrderEvent ORM model (same schema as 12_cursor_pagination)
  main.py              # FastAPI app + lifespan
  routers/
    health.py          # /healthz, /readyz
  streaming/           # The streaming module — one file per use case
    __init__.py        # Aggregator router mounted at /stream
    _common.py         # iter_rows() — the shared server-side cursor primitive
    export.py          # /stream/export.csv
    report.py          # /stream/report.ndjson
    feed.py            # /stream/feed.ndjson
    chunked.py         # /stream/chunked.ndjson — short-tx chunking pattern
docker/
  postgres/init/01_schema.sql
docker-compose.yml
scripts/
  ingest.py            # Bulk-load CSV with asyncpg COPY
```

## Quick start

### 1. Set up the venv

```bash
uv init                          # already done in this repo
uv venv streamvenv               # create the venv
source streamvenv/bin/activate
uv sync --active                 # install runtime + dev deps into streamvenv
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

The host port is **5433** (not 5432) so this stack can run alongside the
sibling `12_cursor_pagination` project, which uses 5432.

### 3. Load data

Reuse the CSV from `12_cursor_pagination`:

```bash
cp ../12_cursor_pagination/data/order_events_1m.csv data/
uv run --active python -m scripts.ingest
```

Or point at any other CSV with the same columns via `CSV_PATH`.

### 4. Run the app

```bash
uv run --active uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Open [http://localhost:8001/docs](http://localhost:8001/docs).

## Trying the endpoints

### Export a subset as CSV

```bash
# Whole dataset
curl -sN 'http://localhost:8001/stream/export.csv' -o order_events.csv

# Filtered (status + country)
curl -sN 'http://localhost:8001/stream/export.csv?status=paid&country=US' \
  -o paid_us.csv

# Watch bytes flow in real time
curl -sN 'http://localhost:8001/stream/export.csv' | head -n 20
```

`-N` (`--no-buffer`) is important — without it `curl` buffers the response
and you can't observe the streaming behaviour.

### Generate a streaming report

```bash
curl -sN 'http://localhost:8001/stream/report.ndjson?progress_every=100000'
```

You'll see lines like:

```jsonl
{"type":"meta","started_at":"...","filters":{"status":null},"progress_every":100000}
{"type":"progress","rows_scanned":100000,"running_total_amount":"5123987.42"}
{"type":"progress","rows_scanned":200000,"running_total_amount":"10245102.01"}
...
{"type":"summary","rows_scanned":1000000,"total_amount":"...","by_status":{...}}
```

### Feed a downstream consumer

```bash
# First chunk — note the resumable `id` cursor
curl -sN 'http://localhost:8001/stream/feed.ndjson?limit=5'

# Resume after a known id
curl -sN 'http://localhost:8001/stream/feed.ndjson?after_id=12345&limit=5'
```

#### "Is it just returning JSON data?" — no, it's the difference that matters

It looks like JSON on the wire, but the *protocol shape* is different from a
normal `GET /events` endpoint, and that's the whole point.

**1. The format is NDJSON, not a JSON array.**
A regular endpoint returns a single document:

```json
[ {"id": 1, ...}, {"id": 2, ...}, {"id": 3, ...} ]
```

The consumer has to wait for the closing `]` before it can parse anything,
because that's how JSON works — it's not valid until it's complete.

The feed returns **one JSON object per line**, no enclosing array, no commas
between records:

```
{"id": 1, ...}\n
{"id": 2, ...}\n
{"id": 3, ...}\n
```

Each line is a complete, valid JSON document on its own. The consumer can
`readline()` → `json.loads()` → process → repeat. This is the same format
Kafka REST proxies, ElasticSearch's `_bulk`, and most ETL tools use for
exactly this reason.

**2. The connection is long-lived.**
A typical request/response cycle is milliseconds. This one stays open for
minutes or hours — the server keeps writing rows until the client
disconnects or `STREAM_MAX_ROWS` is hit. From the consumer's perspective,
it's closer to "subscribe to a topic" than "fetch a resource."

**3. It's resumable, not paginated.**
Pagination uses an opaque `next_cursor` the client has to remember and pass
back. The feed uses `?after_id=N` — the consumer just remembers the **last
`id` it successfully processed** and resumes from there after a crash,
deploy, or network blip. No pagination metadata is needed because the
ordering (`ORDER BY id`) and the cursor (`WHERE id > :after_id`) are both
trivial integers.

**4. It respects backpressure automatically.**
If the downstream consumer is slower than the database, the TCP socket's
send buffer fills up. The `yield` in the async generator then blocks, which
suspends the `async for` over the DB cursor, which stops asking PostgreSQL
for more rows. Memory stays flat no matter how slow the consumer is — you
never accumulate a backlog in the API process.

#### A realistic consumer (Python)

```python
import json, httpx

last_id = load_checkpoint() or 0    # e.g. read from Redis or a file

with httpx.stream(
    "GET",
    "http://localhost:8001/stream/feed.ndjson",
    params={"after_id": last_id},
    timeout=None,                    # never time out on a long-lived stream
) as resp:
    for line in resp.iter_lines():
        if not line:
            continue
        event = json.loads(line)
        process(event)               # write to warehouse, push to Kafka, etc.
        last_id = event["id"]
        save_checkpoint(last_id)     # durably remember progress
```

Notice what's missing: no pagination loop, no `next_cursor` accounting, no
"give me the next page" round-trip. The consumer drives at its own pace, and
when it crashes, it resumes from the last checkpointed `id`.

#### What this endpoint is *not*

- **Not push-based.** It's still HTTP — the consumer initiates the
  connection. Real push (WebSockets, SSE, gRPC server-streaming) is a
  superset of this; NDJSON over plain HTTP is the lowest-common-denominator
  version that works through any proxy, firewall, and HTTP client.
- **Not exactly-once.** Crashes between `process(event)` and
  `save_checkpoint(last_id)` will replay the event. Downstream consumers
  must be idempotent — usually by upserting on `(id)`.
- **Not a live feed of new inserts.** It streams what's already in the
  table. Tailing newly-inserted rows would need either polling
  (`after_id=last_seen`, re-request when you hit EOF) or a real CDC source
  like Postgres logical replication.

### Chunk everything (even when streaming)

```bash
# First N rows, default chunk size
curl -sN 'http://localhost:8001/stream/chunked.ndjson?limit=5'

# Resume after a known id, with an explicit chunk size
curl -sN 'http://localhost:8001/stream/chunked.ndjson?after_id=12345&chunk_size=10000'

# Filter by status, drain the rest in 50k-row chunks
curl -sN 'http://localhost:8001/stream/chunked.ndjson?status=paid&chunk_size=50000' \
  | wc -l
```

#### What it is

The other three endpoints open **one** PostgreSQL server-side cursor and walk
it for the entire response. That's efficient, but the database has to keep a
transaction open the whole time. If the client reads slowly (a flaky network,
a downstream worker that pauses), that transaction stays open for minutes or
hours. While it's open, PostgreSQL:

- Holds locks acquired by the read.
- Cannot vacuum dead tuples the transaction can still see.
- Counts the connection against `idle_in_transaction_session_timeout`.
- Pins one connection from your pool.

The **chunking pattern** keeps the *streaming* property — bytes go out the
moment the first row arrives — but replaces "one long transaction" with "many
short ones." Each chunk is a self-contained `SELECT ... WHERE id > :last_id
ORDER BY id LIMIT N`, runs in its own transaction, and closes before the next
chunk starts.

#### Step-by-step overview

1. **Client opens the stream** with an optional `?after_id=` cursor — the
   last id it successfully processed, or `0` for a fresh start.
2. **Server opens a fresh `AsyncSession`** for chunk #1.
3. **Server runs one bounded SELECT**:
   ```sql
   SELECT * FROM order_events
   WHERE id > :last_id
   ORDER BY id
   LIMIT :chunk_size;
   ```
4. **Server closes the session** (transaction commits).
5. **Server yields each row** of the chunk to the response as one NDJSON
   line. TCP backpressure applies: if the client reads slowly, the `yield`
   blocks — and crucially, **no DB connection is held while it blocks.**
6. **Server advances the cursor**: `last_id = rows[-1].id`.
7. **Repeat from step 2** until a chunk comes back smaller than
   `chunk_size` (drained) or `STREAM_MAX_ROWS` / `?limit=` is hit.

#### Why each step matters

| Step                              | Why it's that way                                                                                                                                                                                  |
|-----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fresh session per chunk           | A session that's only alive for the duration of one SELECT cannot hold a transaction open across the slow part — the network write to the client.                                                  |
| `WHERE id > :last_id ORDER BY id` | Keyset pagination. Uses the primary-key B-tree, so each chunk is an index range scan — O(chunk_size), not O(table). No `OFFSET`, no skipping work.                                                 |
| `LIMIT :chunk_size`               | Bounds memory per chunk to a known number of rows. The whole loop is constant-memory regardless of dataset size.                                                                                   |
| Close session *before* yielding   | This is the whole point of the pattern. The yield is the part that can block on a slow client; doing it after the session has closed means no transaction is held during that block.               |
| Partial chunk → break             | If the DB returns fewer rows than asked for, we've drained the matching rows. Skipping the next round-trip avoids one wasted empty SELECT at end of stream.                                        |

#### How it's implemented in this project

The endpoint lives at [`app/streaming/chunked.py`](app/streaming/chunked.py)
and is wired into the aggregator router in
[`app/streaming/__init__.py`](app/streaming/__init__.py).

Key implementation choices:

- **Bypasses the `get_session` dependency on purpose.** `get_session` would
  open one session for the whole request, which is exactly the long-lived
  shape we're trying to avoid. Instead, the endpoint grabs the
  `async_sessionmaker` from `app.db` and opens a new session inside the
  generator, one per chunk:
  ```python
  async with sessionmaker() as session:
      result = await session.execute(stmt)
      rows = result.scalars().all()
  # session and its transaction are closed HERE,
  # before we yield rows to the client.
  for row in rows:
      yield (json.dumps(_serialize(row)) + "\n").encode("utf-8")
  ```
- **Uses `.scalars().all()` deliberately.** Loading one chunk into memory is
  fine — `chunk_size` is bounded. The thing we *don't* want is the open
  cursor that `session.stream()` would create.
- **Same row projection as the feed.** A plain `_serialize(row) -> dict` so
  per-row cost stays low across millions of rows.
- **Sends NDJSON with `X-Accel-Buffering: no`.** One JSON object per line,
  no enclosing array — the consumer reads line-by-line and never waits for
  a closing `]`.

#### Query parameters

| Param         | Default              | Meaning                                                                |
|---------------|----------------------|------------------------------------------------------------------------|
| `after_id`    | `0`                  | Resume strictly after this id. Pass the last id you saw.               |
| `status`      | unset                | Filter rows by `status` column.                                        |
| `chunk_size`  | `STREAM_CHUNK_SIZE`  | Rows per SELECT. Bigger = fewer round-trips; smaller = shorter txns.   |
| `limit`       | `STREAM_MAX_ROWS`    | Hard cap on rows served. Production consumers leave this unset.        |

#### When to pick chunked over feed/export/report

- **You expect slow consumers.** ETL jobs that pause to apply backpressure,
  flaky network paths, anything that may stall mid-stream.
- **You care about transaction duration on the DB side.** Long-running
  transactions interfere with autovacuum and can trip
  `idle_in_transaction_session_timeout`.
- **You want trivial restartability.** A chunked stream's "what's the
  retry?" answer is always: pass the last id you saw as `after_id`.
- **You want the response shape to mirror your batch jobs.** If your
  background workers already use the `WHERE id > last_id LIMIT N` loop,
  this endpoint is the streaming surface of the same pattern.

Pick the server-side-cursor endpoints (`export.csv`, `report.ndjson`,
`feed.ndjson`) when the consumer is fast, the dataset is read in one sitting,
and one open transaction for the duration of the response is fine.

## Tuning

Set in `.env`:

| Var                  | Default | What it does                                           |
|----------------------|---------|--------------------------------------------------------|
| `STREAM_CHUNK_SIZE`  | `1000`  | Rows fetched per DB round-trip. Bigger = fewer trips, more memory per chunk. |
| `STREAM_MAX_ROWS`    | `0`     | Hard cap per request. `0` = unbounded. Belt for runaway exports. |
| `DB_POOL_SIZE`       | `10`    | Connections in the pool. Each in-flight stream holds one. |
| `DB_MAX_OVERFLOW`    | `20`    | Overflow above pool size. |

## Why streaming, recap

A non-streamed handler like

```python
@app.get("/export")
async def export_logs():
    rows = (await session.execute(select(OrderEvent))).scalars().all()
    return [OrderEventOut.model_validate(r) for r in rows]   # OOM territory
```

does three things wrong at scale:

1. Loads every row into memory (`scalars().all()`).
2. Builds a Python list of Pydantic models alongside the raw rows.
3. Waits to send a single byte until all of the above is done — time-to-first-byte equals total query time.

The streamed version fixes all three: bounded memory, no list materialisation,
first byte goes out the moment the first row arrives.

## Mental Model: APIs as Data Pipelines

Once data grows large, every endpoint should be viewed as a pipeline:

$$\text{Database} \rightarrow \text{Filter} \rightarrow \text{Chunk} \rightarrow \text{Stream} \rightarrow \text{Client}$$

Each stage should:

* Have bounded memory
* Be independently optimizable
* Fail without cascading

How the four endpoints in this project map onto that pipeline:

| Stage      | Where it lives                                                                                                                                  |
|------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| Database   | Postgres + the `(created_at, id)` and `status` indexes from `docker/postgres/init/01_schema.sql`. The data layer is the only place row-count lives. |
| Filter     | `WHERE status = ...` / `WHERE country = ...` / `WHERE id > :after_id` clauses built per-request in each router. Push the predicate to the DB, never to Python. |
| Chunk      | `STREAM_CHUNK_SIZE` — either as `yield_per` on a server-side cursor (`_common.iter_rows`) or as `LIMIT` on each short transaction (`chunked.py`).        |
| Stream     | FastAPI `StreamingResponse` wrapping an `async def ... yield` generator. TCP backpressure flows from the client all the way back to the cursor.         |
| Client     | `curl -N`, an NDJSON consumer with a checkpoint, or a CSV-aware tool. Drives the pipeline at its own pace.                                              |

**Bounded memory** is enforced at the chunk stage: nothing in the pipeline
ever holds more than `STREAM_CHUNK_SIZE` rows. **Independent optimizability**
shows up in the knobs — you can grow the chunk size for throughput, add an
index for the filter, swap the streaming format, or change the consumer
checkpoint strategy without touching the other stages. **Fail without
cascading** is what the `chunked.ndjson` endpoint buys you most directly: if
any stage stalls, the open transaction has already closed and the consumer
can resume from the last `id` it saw — no replaying from the top, no orphaned
DB state.
