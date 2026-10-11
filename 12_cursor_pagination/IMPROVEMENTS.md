# Future Improvements

This project intentionally stops at "minimal but scalable". Here is the road from this baseline to a real production system, grouped by what hurts first as load grows.

---

## 1. Database scaling

### Partitioning
Once `order_events` crosses ~100M rows, range-partition by `created_at` (monthly or weekly). The cursor query already filters on `created_at` so the planner can prune partitions for free.
- **Tradeoff:** writes become slightly slower (partition routing); maintenance overhead for new partitions (use `pg_partman`).
- **Win:** vacuum + bloat stay bounded per partition; old partitions can be detached and archived cheaply.

### Read replicas
Pagination is read-heavy. Route `/events` to streaming replicas and keep the primary for writes.
- **Tradeoff:** replication lag — clients may briefly see "old" cursor positions. For keyset this is harmless; for OFFSET it's a correctness bug. Another point in favour of cursors.

### Sharding
At billions of rows, shard by `customer_id` (or whatever your tenant key is). Cursors become `(shard_id, created_at, id)` and the API fans out per request.
- Consider Citus or move hot tenants to dedicated shards before going fully horizontal — it's cheaper.

### pgBouncer
The async engine pool is per-process. Behind 8 Uvicorn workers × `pool_size=10` that's 80 connections — workable. Above that, put **pgBouncer in transaction pool mode** in front and drop SQLAlchemy's pool size to 1–2.

### TimescaleDB / ClickHouse
For pure time-series analytics on the same data, a TimescaleDB hypertable or a ClickHouse mirror gives you 10–100× faster range scans and compression. Keep Postgres as the system-of-record.

---

## 2. Ingestion

### `psycopg3` COPY
asyncpg's `copy_records_to_table` is fast, but for the absolute floor latency consider psycopg3's `cursor.copy()` with `pyarrow`/Arrow IPC for zero-copy column transfer.

### Apache Arrow / DuckDB preprocessing
Read the CSV into Arrow once, run schema inference + cheap transforms in DuckDB, then COPY the Arrow buffer into Postgres. Useful when source files need cleaning before ingest.

### Kafka ingestion
Replace one-shot CSV imports with a Kafka topic + a consumer that batches events and COPY-loads them every N seconds. Resumability becomes Kafka offsets — much simpler than `MAX(id)`.

### Async workers
Use **Arq** / **Taskiq** / **RQ** for backfills and reindex jobs. Keeps the API process responsive.

---

## 3. Caching

### Redis page cache
For the **first** page (the most-hammered one) cache the response by `(filters, limit)` in Redis with a short TTL (5–30s). Don't cache deep pages — they're rare and the cursor already keys them naturally.

### Materialised views
If you expose aggregated endpoints (`/events/by-day`), back them with a `REFRESH MATERIALIZED VIEW CONCURRENTLY` on a schedule. The cursor pattern still works on the view.

---

## 4. Observability

- **structlog** with JSON output → ship to Loki / CloudWatch.
- **OpenTelemetry** auto-instrumentation for FastAPI + SQLAlchemy + asyncpg gives you end-to-end traces — invaluable when chasing a slow page.
- **Prometheus + Grafana**: request latency histograms (`http_request_duration_seconds`), DB pool gauges (`sqlalchemy_pool_*`), connection counts.
- Log the **EXPLAIN** plan in dev for any query above a latency threshold — catches regressions when an index gets dropped accidentally.

---

## 5. Deployment

### Kubernetes
- API deployment with HPA on RPS or p95 latency.
- Postgres on a managed service (RDS / Cloud SQL / Aiven) for HA + PITR; don't self-host until you have a DBA.
- pgBouncer as a sidecar **or** a separate Deployment behind a Service — sidecar is simpler, Deployment is more efficient at scale.

### CI/CD
GitHub Actions matrix: lint (ruff) → tests → build image → push → deploy. Block merges on a perf test that runs `/events` at 3 page depths and asserts p99 stays flat.

### Security
- **JWT auth** via FastAPI's `OAuth2PasswordBearer` or an API gateway.
- TLS terminated at the gateway; mTLS to the DB if you self-host.
- Treat the cursor as opaque, **don't sign it** — it doesn't contain secrets. But if you ever encode user-tenant info into a cursor, HMAC-sign it.

---

## 6. Load testing

### k6
Smallest setup. Script: ramp from 1 to 200 VUs, walk pages randomly with `cursor` extracted from the previous response. Watch p95 stay flat — that's the whole point of the project.

### Locust
Better when you want a UI and a more realistic mix of endpoints/users. Same approach: stateful users that hold their own cursor between requests.

---

## 7. Cursor edge cases

- **Concurrent inserts during pagination.** Keyset is naturally stable here: a new row appears in a future page, never duplicated in a past one. OFFSET cannot make that guarantee.
- **Concurrent deletes.** If the row at the cursor position is deleted, the next page just resumes after it — no error. Be aware that "I have N pages" guarantees vanish; treat the API as a stream, not a fixed table.
- **MVCC + long-running paginators.** A client holding a cursor for hours is fine because we're not relying on a snapshot — each request is independent and indexed.
- **VACUUM / HOT updates.** Keep `autovacuum_naptime` low for hot tables. HOT updates (when the indexed columns aren't touched) keep the cursor index lean — another argument for *not* updating `created_at` after insert.
- **Tampered cursors.** Already returned as `400` by `Cursor.decode`. If cursors ever encode privileged info, sign them with HMAC.

---

## Roadmap (rough order)

1. Add structured logging + Prometheus metrics (1 day).
2. Put pgBouncer in front, drop pool to 2 per worker (½ day).
3. Add an `/events:export` streaming endpoint via NDJSON + `session.stream()` (1 day).
4. Switch ingestion to Kafka + Arq consumer (3 days).
5. Range-partition `order_events` by month (1–2 days incl. backfill).
6. Read-replica routing for `/events` (2 days incl. infra).
7. Sharding — only when the above stops being enough.

The point is: keyset pagination is the foundation that makes every later step possible. Get it right first.
