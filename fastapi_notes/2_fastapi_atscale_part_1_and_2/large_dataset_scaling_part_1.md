# FastAPI at Scale (Part 1): Handling Millions of Rows Without Killing Your Server

What actually breaks first when your FastAPI app meets real data.

---

## Introduction

FastAPI feels magical when you’re starting out.

You define a model, write an endpoint, hit `/docs`, and suddenly you have a clean, blazing-fast API. For small to medium datasets, it performs exceptionally well, often surpassing heavier frameworks with significantly less effort.

Then one day, the dataset grows.

Not gradually. Not politely.

Suddenly, you’re asked to expose millions of rows:

* Audit logs
* Transactional records
* Historical events
* Exports for analytics

And that’s when things start to fall apart.

* Requests hang.
* Workers spike to 100% memory.
* Databases slow down for everyone, not just your service.

Why does this happen, and more importantly, how can we design FastAPI endpoints that remain stable when the data size becomes unmanageable?

---

## The Illusion of “Fast” in FastAPI

A common misconception is:

> “FastAPI is async, so it should handle large data easily.”

Async helps with waiting, not with volume.

When you return millions of rows:

1. Python still needs to hold them in memory
2. Pydantic still needs to serialize them
3. The event loop is still blocked during serialization
4. The response still needs to travel over the network

FastAPI can be fast — but it cannot save you from poor data handling decisions.

---

## The First Mistake Everyone Makes

At some point, almost every developer writes something like this:

```python
@app.get("/events")
async def get_events():
    rows = await database.fetch_all("SELECT * FROM events")
    return rows

```

It works. It passes tests. It even feels clean.

And it is also the single fastest way to:

* Exhaust RAM
* Freeze your worker
* Trigger timeouts
* Bring down adjacent services

### Why?

Because this endpoint tries to do everything at once:

* Fetch everything
* Hold everything
* Serialize everything
* Send everything

At scale, this is not an endpoint; it’s a denial-of-service attack on your own server.

---

## Scaling Rule #1: Data Volume Is a System Design Problem

Handling millions of rows is not an API problem. It’s a pipeline problem.

Whenever large datasets are involved, you should stop thinking in terms of:

> “How do I return this data?”

And start thinking:

> “How does this data flow through my system?”

That shift in thinking is what separates stable systems from fragile ones.

---

## Principle #1: Never Fetch What You Don’t Need

The most silent performance killer in large APIs is `SELECT *`.

* At a small scale, it doesn’t matter.
* At a large scale, it’s disastrous.

Every extra column:

* Consumes memory
* Slows serialization
* Increases network payload
* Wastes CPU cycles

### ❌ The Hidden Cost of SELECT *

```sql
SELECT * FROM events;

```

Even if your client only needs 3 fields, the database:

* Reads every column
* Sends every byte
* Forces Python to deserialize everything

### ✅ Be Explicit, Always

```sql
SELECT id, status, created_at
FROM events
WHERE created_at >= NOW() - INTERVAL '7 days';

```

This does three important things:

1. Reduces memory footprint
2. Improves cache efficiency
3. Makes intent obvious to future readers

At scale, clarity becomes performance.

---

## Principle #2: Pagination Is Not a Feature — It’s a Requirement

If an endpoint can return an unbounded number of rows, it is already broken. The only question is when it will fail.

### Why Offset Pagination Fails Quietly

```sql
SELECT * FROM logs
ORDER BY id
LIMIT 1000 OFFSET 500000;

```

This looks harmless. It isn’t. The database still:

1. Scans 500,000 rows
2. Discards them
3. Then returns the next 1,000

As offsets grow:

* Queries slow down linearly
* CPU usage spikes
* Indexes stop helping

Your API becomes slower with time, even if traffic stays constant.

### Cursor-Based Pagination: The Scalable Default

```sql
SELECT * FROM logs
WHERE id > :last_id
ORDER BY id
LIMIT 1000;

```

This works because:

* The database uses indexes efficiently
* Each page costs roughly the same
* Performance does not degrade over time

#### Async FastAPI Example

```python
@app.get("/logs")
async def get_logs(last_id: int = 0, limit: int = 1000):
    query = """
        SELECT id, message, created_at
        FROM logs
        WHERE id > :last_id
        ORDER BY id
        LIMIT :limit
    """
    rows = await database.fetch_all(
        query, {"last_id": last_id, "limit": limit}
    )
    return rows

```

This endpoint will behave predictably, whether there are:

* 10,000 rows
* 1 million rows
* 50 million rows

That predictability is the foundation of scale.

---

## Principle #3: Large Responses Must Be Streamed

If your endpoint:

* Exports data
* Generates reports
* Feeds downstream systems

Then returning a giant JSON list is the worst possible choice.

### Why Streaming Changes Everything

Streaming flips the model:

* You don’t wait for all the data
* You don’t hold everything in memory
* You send results as they’re produced

### Streaming in FastAPI

```python
from fastapi.responses import StreamingResponse

async def stream_rows():
    async for row in database.iterate(
        "SELECT id, message FROM logs"
    ):
        yield f"{row['id']},{row['message']}\n"

@app.get("/export")
async def export_logs():
    return StreamingResponse(
        stream_rows(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"}
    )

```

This approach:

* Uses constant memory
* Improves time-to-first-byte
* Handles massive datasets safely

Streaming is not an optimization; it’s survival.

---

## Principle #4: Chunk Everything (Even When Streaming)

Streaming does not mean “one massive query.”

Databases don’t like long-running queries. They hold locks, consume resources, and fail badly under pressure.

### Chunking Pattern

```python
CHUNK_SIZE = 100_000
last_id = 0

while True:
    rows = await database.fetch_all(
        """
        SELECT * FROM events
        WHERE id > :last_id
        ORDER BY id
        LIMIT :limit
        """,
        {"last_id": last_id, "limit": CHUNK_SIZE}
    )
    if not rows:
        break
    process(rows)
    last_id = rows[-1]["id"]

```

Chunking gives you:

* Short transactions
* Failure recovery
* Controlled memory growth

It turns dangerous operations into manageable units of work.

---

## Mental Model: APIs as Data Pipelines

Once data grows large, every endpoint should be viewed as a pipeline:


$$\text{Database} \rightarrow \text{Filter} \rightarrow \text{Chunk} \rightarrow \text{Stream} \rightarrow \text{Client}$$

Each stage should:

* Have bounded memory
* Be independently optimizable
* Fail without cascading

---

## Closing Thoughts (Part 1)

FastAPI does not collapse under scale. Undisciplined data handling does.

If you remember only one thing from this article, let it be this:

> Large datasets demand structure, not cleverness.

### In Part 2, we’ll look at:

* Why async is not enough
* When to move work out of requests
* Background jobs and parallel processing
* Keeping your API responsive under load