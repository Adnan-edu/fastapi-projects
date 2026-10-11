# Order Events Data Overview

This project ingests a 1,000,000-row CSV dataset into PostgreSQL and exposes it through a FastAPI app using cursor pagination. The reusable pieces are the table schema, the CSV ingestion flow, and the `(created_at, id)` pagination contract.

## Source data

- CSV file: `data/order_events_1m.csv`
- Row count: `1,000,000` data rows plus one header row
- Header:

```text
id,order_id,customer_id,event_type,status,amount,currency,country,payment_method,product_sku,quantity,created_at,metadata
```

Example rows:

```text
1,1,1129116,placed,pending,22.6,USD,SE,card,SKU02081,2,2024-08-16 14:12:31,source=web;promo=none
2,1,1129116,paid,paid,22.6,USD,SE,card,SKU02081,2,2024-08-16 15:06:31,source=web;promo=welcome10
3,1,1129116,packed,fulfilled,22.6,USD,SE,card,SKU02081,4,2024-08-17 03:57:31,source=web;promo=summer
```

## PostgreSQL table

Table name: `order_events`

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | `BIGINT` | no | Unique event row id and primary key. |
| `order_id` | `BIGINT` | no | Business order id. Multiple events can share one order id. |
| `customer_id` | `BIGINT` | no | Customer associated with the order. |
| `event_type` | `TEXT` | no | Lifecycle event, such as `placed`, `paid`, `packed`, `shipped`, `out_for_delivery`. |
| `status` | `TEXT` | no | Queryable event status, such as `pending`, `paid`, `fulfilled`, `in_transit`. |
| `amount` | `NUMERIC(12,2)` | no | Monetary amount for the order/event snapshot. |
| `currency` | `TEXT` | no | Currency code, for example `USD`. |
| `country` | `TEXT` | no | Country code, for example `SE`. |
| `payment_method` | `TEXT` | no | Payment method, for example `card`. |
| `product_sku` | `TEXT` | no | Product SKU. |
| `quantity` | `INTEGER` | no | Quantity for the event row. |
| `created_at` | `TIMESTAMP` | no | Event timestamp and primary sort key for pagination. |
| `metadata` | `TEXT` | yes | Semi-structured key/value text, for example `source=web;promo=none`. |

Reusable schema file: `utils/order_events_schema.sql`.

## Indexes

```sql
CREATE INDEX ix_order_events_created_at_id
    ON order_events (created_at, id);

CREATE INDEX ix_order_events_customer_id
    ON order_events (customer_id);

CREATE INDEX ix_order_events_status
    ON order_events (status);
```

The most important index is `(created_at, id)`. It supports deterministic keyset pagination:

```sql
WHERE (created_at, id) > (:cursor_created_at, :cursor_id)
ORDER BY created_at, id
LIMIT :limit_plus_one
```

`created_at` gives the chronological order. `id` is the tie-breaker that makes the order stable when multiple rows have the same timestamp.

## Ingestion flow

The Docker Postgres container bootstraps the table through `docker/postgres/init/01_schema.sql` on first volume creation. The Python ingestion script can also create the table if it is missing.

Main ingestion behavior:

1. Reads database URL from `ASYNCPG_URL`.
2. Reads CSV path from `CSV_PATH` or `--csv`.
3. Validates that the CSV header exactly matches the expected columns.
4. Streams CSV rows instead of loading the whole file into memory.
5. Converts values to Python types before loading:
   - integer ids and quantity
   - `Decimal` amount
   - `datetime` created_at
   - empty metadata to `NULL`
6. Loads batches with asyncpg `copy_records_to_table`, which uses PostgreSQL COPY.
7. Resumes safely by reading `MAX(id)` from `order_events` and skipping CSV rows already loaded.
8. Runs `ANALYZE order_events` after ingestion so PostgreSQL has fresh planner statistics.

Reusable loader: `utils/ingest_order_events.py`.

## Docker layout

`docker-compose.yml` defines two services:

- `postgres`: PostgreSQL 16 Alpine, persisted in the `pgdata` named volume.
- `api`: FastAPI app container built from `docker/Dockerfile`.

Important Docker details:

- Postgres init SQL is mounted from `./docker/postgres/init` to `/docker-entrypoint-initdb.d`.
- The local `./data` folder is mounted read-only into the API container at `/app/data`.
- API connects to Postgres with `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/...`.
- Ingestion uses raw `ASYNCPG_URL=postgresql://...@postgres:5432/...`.

Management scripts:

- `scripts/start.sh`: creates `.env` from `.env.example` if needed, starts Postgres, waits for health.
- `scripts/health.sh`: shows container state and runs `SELECT 1`.
- `scripts/stop.sh`: stops containers without deleting the database volume.
- `scripts/restart.sh`: restarts Postgres.
- `scripts/logs.sh`: tails Docker Compose logs.
- `scripts/ingest.py`: project-local ingestion implementation.

## FastAPI data contract

The ORM model maps directly to the `order_events` table. The only naming difference is `metadata`: SQLAlchemy reserves `metadata`, so the Python attribute is `metadata_` while the database column remains `metadata`.

Response item shape:

```json
{
  "id": 1,
  "order_id": 1,
  "customer_id": 1129116,
  "event_type": "placed",
  "status": "pending",
  "amount": "22.60",
  "currency": "USD",
  "country": "SE",
  "payment_method": "card",
  "product_sku": "SKU02081",
  "quantity": 2,
  "created_at": "2024-08-16T14:12:31",
  "metadata_": "source=web;promo=none"
}
```

Page response shape:

```json
{
  "items": [],
  "next_cursor": null,
  "has_more": false
}
```

## Reusing this in another FastAPI app

Copy these files first:

- `utils/order_events_schema.sql`
- `utils/ingest_order_events.py`

Then add equivalent app pieces:

- SQLAlchemy async engine/session setup.
- ORM model matching `order_events`.
- Pydantic response schema.
- Cursor encode/decode helper using `(created_at, id)`.
- Route that queries with `ORDER BY created_at, id`, optional filters, and `LIMIT limit + 1`.

Environment variables to keep:

```text
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
ASYNCPG_URL=postgresql://user:pass@localhost:5432/db
CSV_PATH=data/order_events_1m.csv
INGEST_BATCH_SIZE=50000
DEFAULT_PAGE_LIMIT=50
MAX_PAGE_LIMIT=500
```

When adding filters such as `status`, keep the base `(created_at, id)` index. If a filter becomes highly selective and common, add a composite index like `(status, created_at, id)` for that specific access pattern.
