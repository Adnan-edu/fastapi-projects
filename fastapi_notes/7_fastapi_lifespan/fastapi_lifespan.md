# FastAPI Lifespan: The Modern Way to Manage Application Startup and Shutdown

Every serious backend application has work that must happen before it starts serving requests — and just as important, work that must happen after it stops.

Database connections need to be initialized.
Schemas and tables must exist.
Background resources must be cleaned up properly.

In FastAPI, the modern and recommended way to manage this lifecycle logic is the **Lifespan** feature.

This article explains what FastAPI Lifespan is, why it replaced older patterns, and how to use it correctly in production-ready applications.

---

## What Is FastAPI Lifespan?

FastAPI Lifespan is a mechanism that lets you define:

- **Startup logic** (runs when the app starts)
- **Shutdown logic** (runs when the app stops)

It replaces the older event-based API:

```python
@app.on_event("startup")
@app.on_event("shutdown")
```

These decorators are now **deprecated** (since FastAPI 0.95.0). The new lifespan API offers a cleaner, more flexible approach using async context managers.

---

## Why Lifespan Replaced `@app.on_event`

The older event system worked, but it had several architectural limitations. Startup and shutdown logic are often tightly coupled — for example, opening a database connection pool during startup and closing the same pool during shutdown. With separate decorators, resource ownership becomes fragmented across multiple functions.

The Lifespan API solves this by using a single async context manager that manages the entire application lifecycle in one place.

| Aspect | Old `@app.on_event` | New `lifespan` |
|--------|---------------------|----------------|
| **Structure** | Separate functions for startup/shutdown | Single function with `yield` |
| **Shared state** | Requires global variables | Clean state via `app.state` |
| **Async support** | Mixed sync/async confusion | Proper async context manager |
| **Resource pairing** | Hard to connect init/cleanup | Code before/after `yield` naturally paired |
| **Testing** | Works with `TestClient` | Requires `with TestClient(app)` |

> **Important:** If you provide a `lifespan` parameter, `startup` and `shutdown` event handlers will **no longer be called**. It's all lifespan OR all events, not both.

---

## Basic Lifespan Syntax

Here's the fundamental pattern:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic (before yield)
    print("Application starting...")

    yield

    # Shutdown logic (after yield)
    print("Application shutting down...")

app = FastAPI(lifespan=lifespan)
```

- Everything **before** `yield` executes during startup.
- Everything **after** `yield` executes during shutdown.
- The `yield` represents the period where the application is actively serving requests.

This design follows Python's standard context manager pattern, making resource lifecycle management significantly more predictable and easier to reason about.

---

## Understanding the Lifecycle Flow

A FastAPI application using Lifespan follows this sequence:

```text
Application Process Starts
          │
          ▼
   Startup Logic
(before yield executes)
          │
          ▼
        yield
          │
          ▼
  Application Serves Requests
          │
          ▼
Shutdown Signal Received
          │
          ▼
   Shutdown Logic
(after yield executes)
          │
          ▼
   Process Terminates
```

A critical detail: **if an exception occurs before `yield`, the application never starts accepting requests.** This is desirable because it prevents partially initialized applications from running.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_database_pool()
    await verify_database_connection()

    yield

    await app.state.db.close()
```

If the database verification fails, FastAPI stops startup immediately rather than serving requests in a broken state.

---

## Using `app.state` for Shared Resources

A common mistake is storing long-lived resources in module-level global variables. Instead, FastAPI provides `app.state`, which is specifically designed for application-wide resources.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await create_redis_pool()

    yield

    await app.state.redis.close()
```

Inside endpoints:

```python
from fastapi import Request

@app.get("/users")
async def get_users(request: Request):
    redis = request.app.state.redis
    return {"status": "connected"}
```

**Benefits of `app.state`:**

- Centralized resource management
- Cleaner dependency injection
- Better testability
- Avoids problematic global variables

Many experienced FastAPI developers now treat `app.state` as the canonical location for long-lived application resources.

---

## Production Example: SQLAlchemy Database Connection Pool

This is the most common use case. Here's a complete async SQLAlchemy example:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/dbname"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create engine and connection pool
    app.state.engine = create_async_engine(DATABASE_URL, echo=True)
    app.state.SessionLocal = sessionmaker(
        app.state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Optional: verify connection
    async with app.state.engine.begin() as conn:
        await conn.execute("SELECT 1")

    yield

    # Shutdown: dispose connection pool
    await app.state.engine.dispose()

app = FastAPI(lifespan=lifespan)

# Dependency to get DB session
async def get_db():
    async with app.state.SessionLocal() as session:
        yield session

@app.get("/items/")
async def read_items(db: AsyncSession = Depends(get_db)):
    return {"message": "Items retrieved"}
```

The engine is created **once** at startup and reused throughout the lifetime of the application. When the process shuts down, the engine is disposed gracefully, releasing connection pools correctly.

---

## Production Example: MongoDB Connection

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ✅ Create once - shared across requests
    app.state.mongo = AsyncIOMotorClient(MONGO_URI, maxPoolSize=100)
    await app.state.mongo.admin.command("ping")  # optional health check

    yield

    # ✅ Cleanup on shutdown
    app.state.mongo.close()

app = FastAPI(lifespan=lifespan)
```

---

## Production Example: Background Tasks

Lifespan is also useful for launching long-running workers such as Kafka consumers, RabbitMQ listeners, event processors, cache refresh jobs, and scheduled maintenance tasks.

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

async def periodic_job():
    while True:
        print("Job running...")
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    job = asyncio.create_task(periodic_job())

    yield

    # Cancel background task on shutdown
    job.cancel()
    try:
        await job
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

By managing them inside Lifespan, startup and shutdown behavior remains deterministic.

---

## Production Example: ML Model Loading

```python
from contextlib import asynccontextmanager
import gc
from fastapi import FastAPI

def load_model():
    import time
    time.sleep(3)  # Simulate expensive load
    return "mock_model"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load expensive ML model once at startup
    print("Loading ML model...")
    app.state.model = load_model()
    print("Model loaded!")

    yield

    # Free GPU/memory on shutdown
    del app.state.model
    gc.collect()

app = FastAPI(lifespan=lifespan)

@app.get("/predict")
async def predict(x: float):
    result = app.state.model.predict(x)
    return {"result": result}
```

This avoids loading the model on every request and ensures proper cleanup.

---

## Common Production Use Cases

Lifespan is not limited to databases. Typical startup tasks include:

| Resource | Example |
|----------|---------|
| **Database pools** | `app.state.db = create_async_engine(...)` |
| **Redis connections** | `app.state.redis = await redis.from_url(...)` |
| **HTTP clients** | `app.state.client = httpx.AsyncClient()` |
| **Kafka consumers** | `consumer.start()` |
| **APScheduler jobs** | `scheduler.start()` |
| **ML models** | `app.state.model = load_model()` |
| **Configuration validation** | `validate_environment_variables()` |
| **Health checks** | `await verify_external_services()` |

Real-world teams frequently use Lifespan to initialize caches, observability tooling, metrics collectors, feature flag clients, gRPC channels, WebSocket managers, and authentication providers before the first request arrives.

---

## Handling Errors Correctly

A robust lifespan implementation should always guarantee cleanup. Use `try/finally`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    resource = await initialize_resource()

    try:
        yield
    finally:
        await resource.close()
```

This ensures resources are released even if:

- The application crashes
- A shutdown signal occurs
- An exception is raised during runtime

Without proper cleanup, connection leaks and dangling background tasks become common production issues.

---

## Testing Lifespan with TestClient

**Critical:** When testing, you must use `with TestClient(app)` to trigger lifespan events. Without the context manager, the lifespan never runs.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient

items = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    items["foo"] = {"name": "Fighters"}
    yield
    items.clear()

app = FastAPI(lifespan=lifespan)

@app.get("/items/{item_id}")
async def read_items(item_id: str):
    return items[item_id]

def test_read_items():
    assert items == {}  # Before lifespan

    with TestClient(app) as client:
        # Inside: lifespan has started
        assert items == {"foo": {"name": "Fighters"}}

        response = client.get("/items/foo")
        assert response.status_code == 200
        assert response.json() == {"name": "Fighters"}

    # After: lifespan ended, items cleaned up
    assert items == {}
```

The startup logic runs when entering the `with` block. The shutdown logic runs when exiting it. This allows integration tests to validate resource initialization exactly as it occurs in production.

---

## Important ASGI Detail: Lifespan Runs Per Worker

Under the hood, FastAPI implements the **ASGI Lifespan Protocol**, which defines how servers such as Uvicorn, Hypercorn, and Daphne communicate startup and shutdown events to applications.

An important implication is that **lifespan events run per process and per event loop.**

If you start FastAPI with multiple workers:

```bash
uvicorn main:app --workers 4
```

each worker executes its own lifespan sequence:

- Four workers
- Four startup executions
- Four shutdown executions

Developers must account for this when performing operations such as database migrations, distributed lock initialization, or any one-time global setup — those belong outside the per-worker lifespan (for example, in a separate migration command run before the workers start).

---

## Lifespan vs Dependency Injection

A useful mental model:

| Use Case | Dependency Injection | Lifespan |
|----------|----------------------|----------|
| Per-request resource | ✅ | ❌ |
| Database session | ✅ | ❌ |
| Database engine | ❌ | ✅ |
| Redis client | ❌ | ✅ |
| HTTP client | ❌ | ✅ |
| ML model | ❌ | ✅ |
| Scheduler | ❌ | ✅ |
| Application configuration | ❌ | ✅ |

**Dependency injection** manages resources needed for individual requests.
**Lifespan** manages resources needed for the entire application lifetime.

---

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| **Accessing `app.state` before initialization** | Only access `app.state.X` after startup, inside routes |
| **Using sync blocking code in async lifespan** | Use `async def` and `await` for non-blocking I/O |
| **Not testing with `with TestClient()`** | Lifespan won't run in tests without the context manager |
| **Mixing lifespan + `@app.on_event`** | Use one or the other, not both |
| **Sub-applications** | Lifespan only runs for the **main** app, not mounted sub-apps |
| **Forgetting multi-worker behavior** | Remember each worker runs its own lifespan |

---

## Best Practices for Production

1. **Prefer Lifespan over `@app.on_event`** — the old API is deprecated.
2. **Centralize all initialization** in the lifespan function instead of module-level code.
3. **Wrap third-party async resources** inside lifespan for portability and testability.
4. **Fail startup immediately** if critical dependencies are unavailable — better to crash early than serve broken responses.
5. **Store shared resources in `app.state`** rather than global variables.
6. **Always use `try/finally`** for cleanup to handle crashes gracefully.
7. **Keep startup logic fast** whenever possible; avoid expensive synchronous operations that block the event loop.
8. **Be aware that startup runs once per worker process.**
9. **Test lifespan behavior explicitly** using `with TestClient(app)`.
10. **Add health checks** after startup to verify resources are ready:
    ```python
    @app.get("/health")
    async def health_check(request: Request):
        async with request.app.state.engine.connect() as conn:
            await conn.execute("SELECT 1")
        return {"status": "healthy"}
    ```
11. **Use dedicated utility classes** for complex initialization:
    ```python
    class DatabaseUtility:
        @staticmethod
        async def initialize(): ...
        @staticmethod
        async def shutdown(): ...

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await DatabaseUtility.initialize()
        try:
            yield
        finally:
            await DatabaseUtility.shutdown()
    ```
12. **Log startup/shutdown** for observability:
    ```python
    import logging
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Application starting up")
        yield
        logger.info("Application shutting down")
    ```

---

## Summary

FastAPI Lifespan is the **modern, recommended** way to handle startup and shutdown logic. It replaces the deprecated `@app.on_event` decorators with a single async context manager that:

- Guarantees proper async resource management
- Pairs initialization and cleanup naturally around a single `yield`
- Enables clean shared state via `app.state`
- Works seamlessly with testing when using `with TestClient(app)`
- Aligns with the ASGI Lifespan Protocol for predictable per-worker behavior

Whether you're initializing database pools, loading machine learning models, creating Redis connections, starting schedulers, or managing background workers, Lifespan gives you a single, predictable location to orchestrate those resources.

For modern FastAPI applications, Lifespan is no longer just the recommended pattern — it has effectively become the **standard way** to build production-grade startup and shutdown workflows. Your future self (and your deployments) will thank you.
