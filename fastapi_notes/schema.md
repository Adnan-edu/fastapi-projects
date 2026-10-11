I want you to generate one millions rows synthetic dataset in csv format. Later I will download the csv file. Here is the schema 

# Synthetic Data Schema — E-Commerce Order Events

A schema designed to demonstrate the **FastAPI at Scale** principles (cursor pagination, streaming, chunking) by generating **millions of rows** of realistic, query-friendly data.

---

## Chosen Sector: E-Commerce Order Events

**Why this sector?**

- High-volume by nature — even a mid-sized store produces millions of order events per year (placed, paid, shipped, refunded, cancelled).
- Mirrors the article's examples: audit logs, transactional records, historical events, analytics exports.
- Has natural **time-series characteristics** → perfect for cursor pagination on `id` or `created_at`.
- Has obvious **filterable dimensions** (status, country, payment_method) → great for demonstrating "Never fetch what you don't need."
- Easy to reason about and visualize — anyone understands an order.

---

## Table: `order_events`

| Column            | Type                 | Description                                                                 | Notes for Scale                                  |
|-------------------|----------------------|-----------------------------------------------------------------------------|--------------------------------------------------|
| `id`              | `BIGSERIAL PRIMARY KEY` | Monotonic event id                                                       | **Cursor pagination key** (`WHERE id > :last_id`) |
| `order_id`        | `UUID NOT NULL`      | Logical order identifier (multiple events share one order)                  | Indexed; supports per-order timeline queries     |
| `customer_id`     | `BIGINT NOT NULL`    | FK-style reference to a customer (1M–5M synthetic customers)                | Indexed for "all events by customer"             |
| `event_type`      | `VARCHAR(20) NOT NULL` | `placed`, `paid`, `shipped`, `delivered`, `refunded`, `cancelled`         | Low-cardinality → great for filtering            |
| `status`          | `VARCHAR(20) NOT NULL` | Current order status snapshot at event time                              | Useful for `WHERE status = 'shipped'` examples   |
| `amount_cents`    | `BIGINT NOT NULL`    | Order amount in cents (avoid floats)                                        | Aggregations / analytics workloads               |
| `currency`        | `CHAR(3) NOT NULL`   | ISO 4217 (`USD`, `EUR`, `GBP`, `BDT`, `INR`, …)                             | Low cardinality, ~10 values                      |
| `country_code`    | `CHAR(2) NOT NULL`   | ISO 3166-1 alpha-2 (`US`, `GB`, `DE`, `BD`, …)                              | Demonstrates geo-partitioned filtering           |
| `payment_method`  | `VARCHAR(20)`        | `card`, `paypal`, `wallet`, `cod`, `bank_transfer`                          | Nullable for non-payment events                  |
| `product_sku`     | `VARCHAR(32)`        | SKU of the primary line item                                                | Joins to a `products` lookup if extended         |
| `quantity`        | `INTEGER NOT NULL`   | Item count for the event                                                    | Small int                                        |
| `created_at`      | `TIMESTAMPTZ NOT NULL` | Event timestamp (UTC)                                                     | **Secondary cursor key**, BRIN-friendly          |
| `metadata`        | `JSONB`              | Free-form (device, IP hash, coupon code, etc.)                              | Keep small; don't return unless requested        |

### Recommended Indexes

```sql
CREATE INDEX idx_order_events_id              ON order_events (id);                    -- cursor
CREATE INDEX idx_order_events_created_at      ON order_events USING BRIN (created_at); -- time scans
CREATE INDEX idx_order_events_customer_id     ON order_events (customer_id);
CREATE INDEX idx_order_events_status_created  ON order_events (status, created_at DESC);
CREATE INDEX idx_order_events_country         ON order_events (country_code);
```

### DDL

```sql
CREATE TABLE order_events (
    id              BIGSERIAL    PRIMARY KEY,
    order_id        UUID         NOT NULL,
    customer_id     BIGINT       NOT NULL,
    event_type      VARCHAR(20)  NOT NULL,
    status          VARCHAR(20)  NOT NULL,
    amount_cents    BIGINT       NOT NULL,
    currency        CHAR(3)      NOT NULL,
    country_code    CHAR(2)      NOT NULL,
    payment_method  VARCHAR(20),
    product_sku     VARCHAR(32),
    quantity        INTEGER      NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    metadata        JSONB
);
```

---

## How This Schema Maps to the Article's Principles

| Article Principle                       | Column / Design that demonstrates it                          |
|-----------------------------------------|---------------------------------------------------------------|
| Never fetch what you don't need         | `metadata JSONB` — heavy, exclude it from list endpoints      |
| Cursor-based pagination                 | `id BIGSERIAL` monotonic, indexed                             |
| Streaming exports                       | `created_at` range scans → CSV export endpoints               |
| Chunking                                | `WHERE id > :last_id ORDER BY id LIMIT :chunk` pattern fits   |
| Filter early                            | `status`, `country_code`, `event_type` are low-cardinality    |

---

## Generating Millions of Rows — Practical Tips

The goal is **not** to write a `for i in range(10_000_000)` loop and call `INSERT` ten million times. That will take hours and exhaust RAM. Below are battle-tested approaches.

### 1. Use `Faker` + `psycopg` `COPY` (fastest single-process approach)

`COPY FROM STDIN` is **10–50× faster** than `INSERT`. Stream rows into Postgres directly without building a giant list in memory.

```python
import csv, io, uuid, random
from datetime import datetime, timedelta, timezone
from faker import Faker
import psycopg

fake = Faker()
EVENT_TYPES = ["placed", "paid", "shipped", "delivered", "refunded", "cancelled"]
STATUSES    = ["pending", "paid", "shipped", "delivered", "refunded", "cancelled"]
CURRENCIES  = ["USD", "EUR", "GBP", "BDT", "INR", "JPY"]
COUNTRIES   = ["US", "GB", "DE", "BD", "IN", "JP", "FR", "BR"]
PAY_METHODS = ["card", "paypal", "wallet", "cod", "bank_transfer"]

def row_generator(n: int):
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    for _ in range(n):
        yield (
            str(uuid.uuid4()),
            random.randint(1, 5_000_000),
            random.choice(EVENT_TYPES),
            random.choice(STATUSES),
            random.randint(500, 500_000),          # cents
            random.choice(CURRENCIES),
            random.choice(COUNTRIES),
            random.choice(PAY_METHODS),
            fake.bothify(text="SKU-####-???").upper(),
            random.randint(1, 5),
            start + timedelta(seconds=random.randint(0, 60*60*24*365*2)),
            '{"src":"synthetic"}',
        )

with psycopg.connect("postgresql://user:pass@localhost/shop") as conn:
    with conn.cursor() as cur:
        with cur.copy(
            "COPY order_events "
            "(order_id, customer_id, event_type, status, amount_cents, "
            "currency, country_code, payment_method, product_sku, quantity, "
            "created_at, metadata) FROM STDIN"
        ) as copy:
            for row in row_generator(10_000_000):
                copy.write_row(row)
```

### 2. Drop & Rebuild Indexes Around the Load

Indexes slow inserts dramatically. For bulk loads:

```sql
-- before load
DROP INDEX IF EXISTS idx_order_events_customer_id;
DROP INDEX IF EXISTS idx_order_events_status_created;

-- ... run COPY ...

-- after load
CREATE INDEX idx_order_events_customer_id    ON order_events (customer_id);
CREATE INDEX idx_order_events_status_created ON order_events (status, created_at DESC);
ANALYZE order_events;
```

### 3. Tune Postgres for the Load

Temporarily, while seeding:

```sql
ALTER SYSTEM SET maintenance_work_mem = '2GB';
ALTER SYSTEM SET synchronous_commit  = off;
ALTER SYSTEM SET wal_level           = minimal;   -- if no replication
ALTER SYSTEM SET max_wal_size        = '8GB';
SELECT pg_reload_conf();
```

Revert these after seeding.

### 4. Parallel Generation with `multiprocessing`

For 100M+ rows, split the work across CPU cores. Each worker writes its own CSV file, then load all CSVs in parallel.

```python
from multiprocessing import Pool
def worker(args):
    idx, n = args
    with open(f"chunk_{idx}.csv", "w", newline="") as f:
        w = csv.writer(f)
        for row in row_generator(n):
            w.writerow(row)

with Pool(8) as p:
    p.map(worker, [(i, 1_250_000) for i in range(8)])  # 10M total
```

Then load each with:

```bash
psql -c "\copy order_events(...) FROM 'chunk_0.csv' CSV"
```

### 5. Partition by Time (Optional, for 100M+ rows)

Once you reach hundreds of millions of rows, native partitioning keeps queries fast:

```sql
CREATE TABLE order_events (
    -- same columns ...
) PARTITION BY RANGE (created_at);

CREATE TABLE order_events_2024 PARTITION OF order_events
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE order_events_2025 PARTITION OF order_events
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
```

### 6. Realistic Distributions (don't be uniform)

Real data is skewed. Make your synthetic data behave like production:

- **80/20 customers**: 20% of customers produce 80% of events (`random.choices` with weights).
- **Status skew**: `delivered` is far more common than `refunded`.
- **Time skew**: more events in last 90 days than in the year before.
- **Currency skew**: `USD` and `EUR` dominate.

Skew is what surfaces real pagination & index issues — uniform data hides them.

---

## Sanity Checks After Loading

```sql
-- row count
SELECT count(*) FROM order_events;

-- size on disk
SELECT pg_size_pretty(pg_total_relation_size('order_events'));

-- sample distribution
SELECT status, count(*) FROM order_events GROUP BY status ORDER BY 2 DESC;

-- verify cursor key is monotonic & dense
SELECT min(id), max(id), max(id) - min(id) + 1 AS expected FROM order_events;
```

---

## Suggested Volumes for Experiments

| Goal                             | Rows         | Approx. disk (Postgres) | Generation time (COPY, 1 core) |
|----------------------------------|--------------|--------------------------|--------------------------------|
| Quick local demo                 | 1,000,000    | ~250 MB                  | ~30 s                          |
| Pagination stress test           | 10,000,000   | ~2.5 GB                  | ~5 min                         |
| Streaming / export demo          | 50,000,000   | ~12 GB                   | ~25 min                        |
| Partitioning demo                | 200,000,000+ | ~50 GB+                  | ~2 h (parallel)                |

Start with 10M — it's enough to make `OFFSET 500000` visibly slow and to make `StreamingResponse` clearly better than a list response.
