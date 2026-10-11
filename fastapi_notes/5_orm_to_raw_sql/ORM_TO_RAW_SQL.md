# FastAPI Performance Engineering: Replacing SQLAlchemy ORM with asyncpg + Raw SQL Templates

> A complete end-to-end tutorial inspired by the idea of replacing ORM-heavy database access with high-performance raw SQL. This tutorial expands significantly beyond the original article and includes architecture, benchmarking, implementation details, production considerations, and migration strategies.

---

# Table of Contents

1. Introduction
2. The ORM Performance Problem
3. Understanding Where Time Is Actually Spent
4. Benchmarking Before Optimizing
5. Project Architecture
6. Setting Up FastAPI + PostgreSQL
7. SQLAlchemy ORM Implementation
8. Identifying ORM Bottlenecks
9. Migrating to asyncpg
10. Organizing SQL with Jinja2 Templates
11. Building a Query Layer
12. Connection Pooling
13. Parameterized Queries
14. Pagination
15. Dynamic Filtering
16. Transactions
17. Bulk Operations
18. Query Profiling
19. PostgreSQL Optimization
20. Caching Strategies
21. Security Considerations
22. Testing Strategy
23. Benchmark Results
24. When ORM Still Makes Sense
25. Hybrid Architecture
26. Production Deployment
27. Final Recommendations

---

# Introduction

Many FastAPI applications start with SQLAlchemy.

This is usually the correct decision.

ORMs provide:

* Productivity
* Type safety
* Model relationships
* Migration support
* Reduced boilerplate

However, once applications reach:

* Millions of rows
* Complex analytical queries
* High request throughput
* Heavy join operations

ORM abstraction can become expensive.

This tutorial demonstrates how to:

```text
FastAPI
      ↓
  asyncpg
      ↓
Raw SQL
      ↓
PostgreSQL
```

instead of:

```text
FastAPI
      ↓
SQLAlchemy ORM
      ↓
Generated SQL
      ↓
PostgreSQL
```

---

# The ORM Performance Problem

Consider an analytics dashboard endpoint.

## SQLAlchemy Version

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/analytics/dashboard")
async def dashboard(
    user_id: int,
    db: AsyncSession
):
    result = await db.execute(
        select(Order, User, Product)
        .join(User)
        .join(Product)
        .where(Order.user_id == user_id)
    )

    rows = result.all()

    return [
        {
            "order_id": row.Order.id,
            "user_name": row.User.name,
            "product": row.Product.name,
            "total": row.Order.total
        }
        for row in rows
    ]
```

Looks clean.

But internally SQLAlchemy performs:

```text
Generate SQL
↓
Execute SQL
↓
Receive rows
↓
Instantiate ORM objects
↓
Track object state
↓
Manage relationships
↓
Serialize objects
↓
Return response
```

Every step adds overhead.

---

# Understanding Where Time Is Actually Spent

Many developers assume:

```text
Slow endpoint = Slow database
```

Often incorrect.

Profiling frequently reveals:

| Component            | Time   |
| -------------------- | ------ |
| PostgreSQL Query     | 30 ms  |
| ORM Mapping          | 120 ms |
| Relationship Loading | 200 ms |
| Serialization        | 100 ms |
| Application Logic    | 50 ms  |

Total:

```text
500 ms endpoint
```

while PostgreSQL only needed:

```text
30 ms
```

---

# Benchmark Before Optimizing

Never optimize blindly.

Install:

```bash
pip install py-spy
```

Run:

```bash
py-spy top --pid <PID>
```

Or:

```bash
py-spy record -o profile.svg --pid <PID>
```

Also benchmark SQL:

```sql
EXPLAIN ANALYZE
SELECT ...
```

---

# Project Architecture

Recommended structure:

```text
app/
│
├── api/
│   └── dashboard.py
│
├── db/
│   ├── pool.py
│   ├── queries.py
│   └── templates/
│
├── services/
│
├── models/
│
└── main.py
```

---

# Install Dependencies

```bash
pip install fastapi
pip install uvicorn
pip install asyncpg
pip install jinja2
pip install pydantic
```

---

# PostgreSQL Connection Pool

## db/pool.py

```python
import asyncpg

pool = None

async def init_pool():

    global pool

    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        database="shop",
        min_size=10,
        max_size=50
    )

async def get_pool():
    return pool
```

---

# Startup Hook

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from db.pool import init_pool

@asynccontextmanager
async def lifespan(app: FastAPI):

    await init_pool()

    yield

app = FastAPI(lifespan=lifespan)
```

---

# Why asyncpg?

asyncpg is:

* Native PostgreSQL driver
* Fully asynchronous
* Uses PostgreSQL protocol directly
* Faster than ORM layers

Example:

```python
rows = await conn.fetch(
    """
    SELECT *
    FROM orders
    WHERE user_id = $1
    """,
    user_id
)
```

Notice:

```text
$1
$2
$3
```

These are PostgreSQL parameter placeholders.

Never use string concatenation.

---

# Organizing SQL Using Jinja2

Large SQL strings become messy.

Create:

```text
db/templates/
```

Example:

## dashboard.sql

```sql
SELECT
    o.id,
    o.total,
    u.name AS user_name,
    p.name AS product_name
FROM orders o
JOIN users u
    ON u.id = o.user_id
JOIN products p
    ON p.id = o.product_id
WHERE o.user_id = $1
ORDER BY o.created_at DESC
```

---

# Loading Templates

```python
from jinja2 import Environment
from jinja2 import FileSystemLoader

env = Environment(
    loader=FileSystemLoader("db/templates")
)

template = env.get_template(
    "dashboard.sql"
)

sql = template.render()
```

---

# Query Layer

Create:

## db/queries.py

```python
from db.pool import pool

async def get_dashboard(user_id):

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                o.id,
                o.total,
                p.name
            FROM orders o
            JOIN products p
                ON p.id = o.product_id
            WHERE o.user_id = $1
            """,
            user_id
        )

    return rows
```

---

# FastAPI Endpoint

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def dashboard(user_id: int):

    rows = await get_dashboard(user_id)

    return [
        dict(row)
        for row in rows
    ]
```

---

# Dynamic Filtering

A common challenge with raw SQL.

## dashboard.sql

```sql
SELECT *
FROM orders
WHERE 1=1

{% if start_date %}
AND created_at >= $1
{% endif %}

{% if end_date %}
AND created_at <= $2
{% endif %}
```

Render:

```python
sql = template.render(
    start_date=start_date,
    end_date=end_date
)
```

### Important

When building dynamic queries, ensure parameter positions (`$1`, `$2`, etc.) match the final SQL. In larger systems, many teams use query builders or helper functions to manage parameter numbering safely.

---

# Pagination

Never load everything.

Bad:

```sql
SELECT *
FROM orders
```

Good:

```sql
SELECT *
FROM orders
ORDER BY created_at DESC
LIMIT $1
OFFSET $2
```

---

# Cursor Pagination

Even better:

```sql
SELECT *
FROM orders
WHERE id < $1
ORDER BY id DESC
LIMIT $2
```

Benefits:

* Faster
* Index friendly
* Scales better

---

# Transactions

```python
async with pool.acquire() as conn:

    async with conn.transaction():

        await conn.execute(
            query1
        )

        await conn.execute(
            query2
        )
```

Rollback happens automatically if an exception occurs.

---

# Bulk Inserts

Bad:

```python
for row in rows:
    await conn.execute(...)
```

Good:

```python
await conn.executemany(
    """
    INSERT INTO orders(id,total)
    VALUES($1,$2)
    """,
    records
)
```

Even faster for very large datasets:

```sql
COPY
```

via asyncpg's copy APIs.

---

# Query Profiling

Always inspect execution plans.

```sql
EXPLAIN ANALYZE
SELECT ...
```

Look for:

```text
Sequential Scan
```

on large tables.

Usually indicates missing indexes.

---

# Indexing Example

```sql
CREATE INDEX idx_orders_user_id
ON orders(user_id);
```

Composite index:

```sql
CREATE INDEX idx_orders_user_created
ON orders(user_id, created_at);
```

Often dramatically improves analytics queries.

---

# PostgreSQL Optimization Checklist

### Enable Connection Pooling

```text
asyncpg Pool
```

### Add Indexes

```text
WHERE
JOIN
ORDER BY
```

columns.

### Avoid SELECT *

Use:

```sql
SELECT id,total
```

instead.

### Use EXPLAIN ANALYZE

Before changing code.

---

# Response Models

Use Pydantic.

```python
from pydantic import BaseModel

class DashboardItem(BaseModel):
    order_id: int
    total: float
    product_name: str
```

Return:

```python
return [
    DashboardItem(
        order_id=row["id"],
        total=row["total"],
        product_name=row["product_name"]
    )
    for row in rows
]
```

---

# Caching

Database optimization isn't enough.

Add Redis.

```text
Request
 ↓
Redis
 ↓
PostgreSQL
```

Example:

```python
cache_key = f"dashboard:{user_id}"
```

Cache expensive analytics results.

---

# Security Considerations

Never do:

```python
query = f"""
SELECT *
FROM users
WHERE id={user_id}
"""
```

SQL Injection risk.

Always use:

```python
await conn.fetch(
    """
    SELECT *
    FROM users
    WHERE id=$1
    """,
    user_id
)
```

---

# Testing

Unit Test:

```python
@pytest.mark.asyncio
async def test_dashboard():
    result = await get_dashboard(1)
    assert len(result) > 0
```

Integration Test:

```python
POSTGRES_CONTAINER
↓
FastAPI
↓
asyncpg
```

Use Dockerized PostgreSQL for repeatable tests.

---

# Typical Benchmark Results

Results vary by workload.

A common pattern:

| Metric        | ORM    | asyncpg |
| ------------- | ------ | ------- |
| Query Latency | 150 ms | 40 ms   |
| CPU Usage     | High   | Lower   |
| Memory Usage  | Higher | Lower   |
| Throughput    | Lower  | Higher  |

The biggest gains typically come from:

1. Eliminating N+1 queries
2. Reducing object mapping overhead
3. Returning only required columns
4. Better SQL optimization

Not every application will see dramatic improvements.

---

# When SQLAlchemy Still Wins

Use SQLAlchemy when:

### CRUD Applications

```text
Admin Panels
Backoffice Tools
Internal Dashboards
```

### Rapid Development

```text
Prototype
Startup MVP
Small Team
```

### Complex Domain Models

```text
Relationships
Validation
Business Rules
```

The productivity gains can outweigh the performance cost.

---

# The Hybrid Architecture (Recommended)

Many mature systems use both approaches.

```text
Simple CRUD
      ↓
SQLAlchemy

Analytics
Reporting
Search
Recommendations
High-volume APIs
      ↓
asyncpg
```

Example:

```text
/users
/products
/orders
```

Use ORM.

But:

```text
/analytics
/reports
/recommendations
/search
```

Use raw SQL.

This often delivers the best balance of maintainability and performance.

---

# Production Deployment Checklist

### Connection Pool

```python
min_size=20
max_size=100
```

Tune based on workload.

### Monitoring

Track:

* Query latency
* Pool utilization
* Slow queries
* Cache hit ratio

### PostgreSQL

Enable:

```text
pg_stat_statements
```

Identify expensive queries.

### Logging

Log:

```text
Query duration
Rows returned
Errors
```

---

# Final Recommendations

Do **not** replace SQLAlchemy simply because someone on the internet says raw SQL is faster.

Follow this order:

```text
1. Measure
2. Profile
3. Identify bottleneck
4. Optimize SQL
5. Add indexes
6. Add caching
7. Remove ORM only if necessary
```

For most FastAPI applications:

```text
SQLAlchemy is good enough.
```

For high-throughput analytics workloads:

```text
FastAPI
 + asyncpg
 + PostgreSQL
 + Hand-tuned SQL
```

can provide substantial performance improvements while giving complete visibility into what the database is actually doing.

The strongest engineering approach is rarely "ORM everywhere" or "raw SQL everywhere." It is understanding both tools well enough to use the right one for each part of the system.
