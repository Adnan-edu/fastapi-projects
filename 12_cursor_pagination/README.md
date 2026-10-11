# Cursor-Based Pagination: The Scalable Default

A minimal, production-shaped FastAPI app that demonstrates **keyset (cursor) pagination** over a 1M-row PostgreSQL table.

```
project-root/
├── app/                # FastAPI app (config, db, models, cursor, routers)
├── scripts/            # Ingestion + Docker management scripts
├── docker/             # Dockerfile + Postgres init SQL
├── data/               # order_events_1m.csv lives here
├── docs/               # (reserved for diagrams etc.)
├── tests/              # Cursor encode/decode tests
├── docker-compose.yml
├── pyproject.toml
├── IMPROVEMENTS.md
└── README.md
```

---

## Tech stack

- **Python 3.13**, FastAPI, Uvicorn
- **PostgreSQL 16** (Dockerised, volume-persisted)
- **SQLAlchemy 2.0 async** + **asyncpg**
- **Pydantic v2** + `pydantic-settings`
- **uv** for env + dependency management

---

## 1) Setup

```bash
# create + activate env
uv init
uv venv cursorvenv
source cursorvenv/bin/activate

# install dependencies (pyproject already defines them)
uv sync

# copy env defaults
cp .env.example .env
```

## 2) Start PostgreSQL

```bash
./scripts/start.sh        # brings up postgres, waits for healthcheck
./scripts/health.sh       # show container status + SELECT 1
./scripts/logs.sh         # tail postgres logs
./scripts/stop.sh         # stop without removing the volume
```

The `pgdata` named volume persists across `stop` / `restart`. To wipe everything: `docker compose down -v`.

## 3) Ingest 1M rows

```bash
uv run python -m scripts.ingest
# or:  uv run python -m scripts.ingest --batch-size 100000 --csv data/order_events_1m.csv
```

The script:
- creates `order_events` + the `(created_at, id)` composite index if missing
- streams the CSV in chunks (memory-bounded)
- uses **asyncpg `copy_records_to_table`** (binary COPY) for throughput
- is **resumable**: rerunning skips rows whose `id` is already present
- runs `ANALYZE` at the end so the planner sees fresh statistics

Expect ~1M rows in well under a minute on a modern laptop.

## 4) Run the API

```bash
uv run uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

Or via Docker:

```bash
docker compose up --build
```

---

## 5) Test the pagination

First page:

```bash
curl -s 'http://localhost:8000/events?limit=5' | jq
```

Response:

```json
{
  "items": [ ... 5 rows ... ],
  "next_cursor": "eyJjIjoiMjAyNC0wOC0xNlQxNDoxMjozMSIsImkiOjV9",
  "has_more": true
}
```

Next page — echo the cursor back:

```bash
NEXT=$(curl -s 'http://localhost:8000/events?limit=5' | jq -r '.next_cursor')
curl -s "http://localhost:8000/events?limit=5&cursor=$NEXT" | jq
```

Filter by status:

```bash
curl -s 'http://localhost:8000/events?limit=10&status=paid' | jq
```

Walk all pages in a shell loop:

```bash
cursor=""
while :; do
  url="http://localhost:8000/events?limit=1000"
  [[ -n "$cursor" ]] && url="$url&cursor=$cursor"
  resp=$(curl -s "$url")
  echo "$resp" | jq '.items | length'
  cursor=$(echo "$resp" | jq -r '.next_cursor // empty')
  [[ -z "$cursor" ]] && break
done
```

---

## Why cursor pagination?

### The OFFSET problem

```sql
SELECT * FROM order_events ORDER BY created_at, id OFFSET 900000 LIMIT 50;
```

PostgreSQL must walk and discard the first 900,000 rows before returning any. Cost grows linearly with depth, and at scale the planner often abandons the index and switches to a sequential scan. On 50M rows this is unusable.

### The keyset alternative

```sql
SELECT *
FROM order_events
WHERE (created_at, id) > (:cur_created_at, :cur_id)
ORDER BY created_at, id
LIMIT 51;
```

With `INDEX (created_at, id)` the database performs a single B-tree seek to the cursor position, then a forward scan of exactly `limit + 1` rows. **Cost is independent of page depth.** We fetch `limit + 1` so we know whether `has_more` is true without a separate `COUNT(*)`.

### EXPLAIN ANALYZE

Compare these against the loaded dataset (run inside `psql`):

```sql
EXPLAIN ANALYZE
SELECT * FROM order_events ORDER BY created_at, id OFFSET 900000 LIMIT 50;
```

vs.

```sql
EXPLAIN ANALYZE
SELECT * FROM order_events
WHERE (created_at, id) > ('2024-09-01 00:00:00', 0)
ORDER BY created_at, id LIMIT 50;
```

The keyset query stays in single-digit milliseconds regardless of where in the table the cursor sits.

### Scaling behaviour

| Rows    | OFFSET at deep page         | Keyset                  |
|---------|-----------------------------|-------------------------|
| 10K     | fast (everything in cache)  | fast                    |
| 1M      | tens to hundreds of ms      | sub-millisecond seek    |
| 50M     | seconds, often seq-scan     | still sub-millisecond   |

### Cursor design

The cursor is **opaque** base64url-encoded JSON: `{"c": "<iso ts>", "i": <id>}`.
- Clients must treat it as a black box — only echo back what the server sent.
- Tampered or malformed cursors return `400 Bad Request`.
- Composite `(created_at, id)` ensures a **total order** — two rows sharing `created_at` would otherwise yield an ambiguous cursor position.
- For UUID PKs, use the same shape but compare on `(created_at, uuid)` — works identically because `tuple_(...) > (...)` is supported on any comparable types.

---

## Operational notes

### Connection pooling

`create_async_engine` is configured with `pool_size=10`, `max_overflow=20`. For high-concurrency deployments put **pgBouncer** in front in transaction-pool mode and use small per-process pools — see `IMPROVEMENTS.md`.

### Rate limiting

Out of scope for this minimal demo. In production: use an API gateway (e.g. Envoy, Kong, AWS API Gateway) or a Starlette middleware like `slowapi`.

### Streaming

The page is small and bounded, so we materialise it. If you need to dump large ranges, use `session.stream()` (async server-side cursor) plus a `StreamingResponse` of NDJSON — keeps memory flat.

---

## Troubleshooting

| Symptom                                          | Fix                                                              |
|---|---|
| `connection refused` from app                    | DB not ready — `./scripts/health.sh`, wait for `healthy` status. |
| `relation "order_events" does not exist`         | Run the ingestion script — it creates the schema if missing.     |
| Ingest progress stops / process killed           | Just rerun `uv run python -m scripts.ingest` — it resumes from `MAX(id)`. |
| Page 1 is fast, page N is slow                   | You're probably using OFFSET. The `/events` endpoint here is keyset; if you forked it, check the SQL. |
| EXPLAIN shows a sequential scan                  | Run `ANALYZE order_events;` — the ingest script does this automatically on success. |

---

## Tests

```bash
uv run pytest -q
```

The included tests cover cursor encode/decode round-trips, tamper handling, and URL-safety. End-to-end pagination tests should run against a real Postgres — left as an exercise.



cp .env.example .env && ./scripts/start.sh
uv sync
uv run python -m scripts.ingest
uv run uvicorn app.main:app --reload
curl -s 'http://localhost:8000/events?limit=5' | jq