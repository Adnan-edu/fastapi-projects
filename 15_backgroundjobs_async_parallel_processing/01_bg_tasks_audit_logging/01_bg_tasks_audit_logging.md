# 01 — BackgroundTasks Audit Logging

> **Pattern:** FastAPI's built-in `BackgroundTasks` for lightweight post-response I/O
> **File:** `01_bg_tasks_audit_logging.md` (formerly `project_1.md`)

**Source rules:** Option 1 (lines 121–155) of `backgroundjobs_async_parallel_processing_part_2.md`.

**Goal:** Demonstrate FastAPI's built-in `BackgroundTasks` for jobs that are safe to run inside the same worker process — small I/O like audit logs, single notifications, lightweight bookkeeping. **Not** for heavy CPU or large file generation.

---

## Dataset context

We use the shared dataset at `/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils`:

- **CSV**: `data/order_events_1m.csv` — 1,000,000 rows
- **Table**: `order_events` (Postgres) — columns: `id, order_id, customer_id, event_type, status, amount, currency, country, payment_method, product_sku, quantity, created_at, metadata`
- **Primary sort key**: `(created_at, id)` with a covering index — used for keyset pagination
- **Schema file**: `utils/order_events_schema.sql`
- **Ingestion script**: `utils/ingest_order_events.py` (asyncpg COPY, resumable, batched)

For Project 1 we only **read** from this table on a list endpoint and **append** an audit-log line per request. The dataset is large enough that we can verify the audit task does not block list responses even when the list query is moderately expensive.

---

## What you will build

```
Client ─► GET /orders?customer_id=...
            │
            ├─► returns first page immediately
            │
            └─► BackgroundTasks runs write_audit_log(...) AFTER response is sent
                    │
                    └─► appends a line to audit.log
```

---

## Step 1 — Create the virtual environment with `uv`

```bash
cd /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects
mkdir -p project_1_bg_tasks_audit && cd project_1_bg_tasks_audit

uv init --python 3.12
uv add fastapi 'uvicorn[standard]' sqlalchemy asyncpg pydantic-settings
```

`uv init` creates `pyproject.toml` and `.venv/`. Activate when you need a shell:

```bash
source .venv/bin/activate
```

---

## Step 2 — Verify the data, ingest only if needed

Because the Postgres data lives in a **Docker volume**, it survives container restarts — once ingested, the 1M rows are still there next time you `docker compose up`. So we **verify before ingesting**; re-running the loader on a full table is wasted I/O.

### 2a. Create the shared check script (one-time, lives in `utils/`)

Create `/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py`:

```python
"""Exit 0 if order_events is fully loaded, 1 if it needs ingestion, 2 on connection error."""
import asyncio
import os
import sys
import asyncpg

EXPECTED_ROWS = 1_000_000

async def main() -> int:
    dsn = os.environ.get("ASYNCPG_URL")
    if not dsn:
        print("ASYNCPG_URL not set", file=sys.stderr)
        return 2
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        print(f"connect failed: {e}", file=sys.stderr)
        return 2
    try:
        exists = await conn.fetchval(
            "SELECT to_regclass('public.order_events') IS NOT NULL"
        )
        if not exists:
            print("status=missing_table")
            return 1
        count = await conn.fetchval("SELECT COUNT(*) FROM order_events")
        if count >= EXPECTED_ROWS:
            print(f"status=ready rows={count:,}")
            return 0
        if count == 0:
            print("status=empty rows=0")
            return 1
        print(f"status=partial rows={count:,} — re-run ingestion (it is resumable)")
        return 1
    finally:
        await conn.close()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

### 2b. Run the check

```bash
ASYNCPG_URL="postgresql://user:pass@localhost:5432/db" \
uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py
```

Outcomes:

| stdout | exit | action |
|---|---|---|
| `status=ready rows=1,000,000` | `0` | **Skip ingestion** — volume already has your data |
| `status=missing_table` | `1` | Run ingestion below |
| `status=empty rows=0` | `1` | Run ingestion below |
| `status=partial rows=…` | `1` | Run ingestion below — resumable via `MAX(id)` |

### 2c. Conditional ingestion (one-liner)

```bash
export ASYNCPG_URL="postgresql://user:pass@localhost:5432/db"
export CSV_PATH="/Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/data/order_events_1m.csv"

uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/check_ingested.py \
  && echo "data ready — skipping ingest" \
  || uv run python /Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/utils/ingest_order_events.py
```

The ingestion script is **resumable** — it reads `MAX(id)` and skips already-loaded rows, then runs `ANALYZE`.

---

## Step 3 — App layout

```
project_1_bg_tasks_audit/
├── pyproject.toml
├── .env
├── audit.log              # created at runtime
└── app/
    ├── __init__.py
    ├── main.py
    ├── db.py
    ├── models.py
    └── audit.py
```

---

## Step 4 — Database + model

```python
# app/db.py
import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]  # postgresql+asyncpg://...

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

```python
# app/models.py
from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, Integer, Numeric, String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger)
    customer_id: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    payment_method: Mapped[str] = mapped_column(String)
    product_sku: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    # SQLAlchemy reserves `metadata`; the DB column stays `metadata`
    metadata_: Mapped[str | None] = mapped_column("metadata", String, nullable=True)
```

---

## Step 5 — The audit task (lightweight I/O)

This is the pattern straight from the article:

```python
# app/audit.py
from datetime import datetime, timezone
from pathlib import Path

AUDIT_FILE = Path("audit.log")

def write_audit_log(user_id: int, path: str, query: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with AUDIT_FILE.open("a") as f:
        f.write(f"{ts}\tuser={user_id}\tpath={path}\tquery={query}\n")
```

> Safe for `BackgroundTasks` because: a single append, no CPU work, no large memory, no risk of starving the worker.

---

## Step 6 — Endpoint

```python
# app/main.py
from fastapi import BackgroundTasks, Depends, FastAPI, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.db import get_session
from app.models import OrderEvent

app = FastAPI(title="Project 1 — BackgroundTasks audit")

@app.get("/orders")
async def list_orders(
    background_tasks: BackgroundTasks,
    customer_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(OrderEvent).order_by(OrderEvent.created_at, OrderEvent.id).limit(limit)
    if customer_id is not None:
        stmt = stmt.where(OrderEvent.customer_id == customer_id)
    if status is not None:
        stmt = stmt.where(OrderEvent.status == status)

    rows = (await session.execute(stmt)).scalars().all()

    # The audit write happens AFTER the response is sent.
    background_tasks.add_task(
        write_audit_log,
        user_id=42,
        path="/orders",
        query={"customer_id": customer_id, "status": status, "limit": limit},
    )

    return {"count": len(rows), "items": [
        {"id": r.id, "order_id": r.order_id, "status": r.status, "amount": str(r.amount)}
        for r in rows
    ]}
```

---

## Step 7 — Run it

```bash
DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db" \
uv run uvicorn app.main:app --reload --port 8001
```

Then:

```bash
curl "http://localhost:8001/orders?status=paid&limit=10"
tail -f audit.log
```

You should see the HTTP response **first**, then the audit line appear.

---

## What this project proves

- ✅ `BackgroundTasks` runs after the response, keeping latency low.
- ✅ Fine for log writes, single email sends, small notifications.
- ❌ **Do not** put report generation, CSV exports, or aggregation here — it runs in the same worker process and will starve `uvicorn` (this is exactly the failure Project 2 fixes).
