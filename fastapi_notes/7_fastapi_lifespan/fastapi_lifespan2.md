## Why FastAPI Replaced `on_event`

The older event system worked, but it had several architectural limitations.

```python
@app.on_event("startup")
async def startup():
    ...

@app.on_event("shutdown")
async def shutdown():
    ...
```

The problem is that startup and shutdown logic are often tightly coupled.

For example:

* Open a database connection pool during startup
* Close the same pool during shutdown

With separate decorators, resource ownership becomes fragmented across multiple functions.

The Lifespan API solves this by using a single async context manager that manages the entire application lifecycle in one place.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application starting...")
    
    yield
    
    print("Application shutting down...")

app = FastAPI(lifespan=lifespan)
```

Everything before `yield` executes during startup.

Everything after `yield` executes during shutdown.

The `yield` represents the period where the application is actively serving requests.

This design follows Python’s standard context manager pattern, making resource lifecycle management significantly more predictable and easier to reason about.

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

A critical detail is that if an exception occurs before `yield`, the application never starts accepting requests.

This is actually desirable because it prevents partially initialized applications from running.

For example:

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

## Production Example: Database Initialization

One of the most common uses of Lifespan is database setup.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://..."

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(DATABASE_URL)

    app.state.engine = engine

    print("Database connected")

    yield

    await engine.dispose()

    print("Database disconnected")

app = FastAPI(lifespan=lifespan)
```

The database engine is created once during startup and reused throughout the lifetime of the application.

When the process shuts down, the engine is disposed gracefully, ensuring that connection pools are released correctly.

---

## Using `app.state` for Shared Resources

A common mistake is storing global variables outside the application.

Instead, FastAPI provides `app.state`, which is specifically designed for application-wide resources.

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

Benefits of `app.state`:

* Centralized resource management
* Cleaner dependency injection
* Better testability
* Avoids problematic global variables

Many experienced FastAPI developers now treat `app.state` as the canonical location for long-lived application resources.

---

## Common Production Use Cases

Lifespan is not limited to databases.

Typical startup tasks include:

### Database Pools

```python
app.state.db = create_async_engine(...)
```

### Redis Connections

```python
app.state.redis = await redis.from_url(...)
```

### HTTP Clients

```python
app.state.client = httpx.AsyncClient()
```

### Kafka Consumers

```python
consumer.start()
```

### APScheduler Jobs

```python
scheduler.start()
```

### Machine Learning Models

```python
app.state.model = load_model()
```

### Configuration Validation

```python
validate_environment_variables()
```

### Health Checks

```python
await verify_external_services()
```

Real-world teams frequently use Lifespan to initialize caches, observability tooling, metrics collectors, feature flag clients, gRPC channels, WebSocket managers, and authentication providers before the first request arrives.

---

## Handling Errors Correctly

A robust lifespan implementation should always guarantee cleanup.

Use `try/finally`.

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

* The application crashes
* A shutdown signal occurs
* An exception is raised during runtime

Without proper cleanup, connection leaks and dangling background tasks become common production issues.

---

## Lifespan and Background Tasks

Lifespan is also useful for launching long-running workers.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(process_events())

    yield

    worker.cancel()
```

Examples:

* Kafka consumers
* RabbitMQ listeners
* Event processors
* Cache refresh jobs
* Scheduled maintenance tasks

By managing them inside Lifespan, startup and shutdown behavior remains deterministic.

---

## Testing Lifespan Logic

FastAPI automatically executes lifespan events when using `TestClient`.

```python
from fastapi.testclient import TestClient

def test_api():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
```

The startup logic runs when entering the `with` block.

The shutdown logic runs when exiting the block.

This allows integration tests to validate resource initialization exactly as it occurs in production.

---

## Important ASGI Detail

Under the hood, FastAPI implements the ASGI Lifespan Protocol.

This protocol is part of the ASGI specification and defines how servers such as:

* Uvicorn
* Hypercorn
* Daphne

communicate startup and shutdown events to applications.

An important implication is that lifespan events run per process and per event loop.

If you start FastAPI with multiple workers:

```bash
uvicorn main:app --workers 4
```

each worker executes its own lifespan sequence.

This means:

* Four workers
* Four startup executions
* Four shutdown executions

Developers must account for this when performing operations such as database migrations or distributed lock initialization.

---

## Lifespan vs Dependency Injection

A useful mental model is:

| Use Case                  | Dependency Injection | Lifespan |
| ------------------------- | -------------------- | -------- |
| Per request resource      | ✅                    | ❌        |
| Database session          | ✅                    | ❌        |
| Database engine           | ❌                    | ✅        |
| Redis client              | ❌                    | ✅        |
| ML model                  | ❌                    | ✅        |
| Scheduler                 | ❌                    | ✅        |
| Application configuration | ❌                    | ✅        |

Dependency injection manages resources needed for individual requests.

Lifespan manages resources needed for the entire application lifetime.

---

## Best Practices

For production systems:

1. Prefer Lifespan over `@app.on_event`.
2. Keep startup logic fast whenever possible.
3. Fail startup immediately if critical dependencies are unavailable.
4. Store shared resources in `app.state`.
5. Always use `try/finally` for cleanup.
6. Be aware that startup runs once per worker process.
7. Test lifespan behavior explicitly.
8. Avoid performing expensive synchronous operations that block the event loop.

Following these principles results in cleaner architecture, fewer resource leaks, and more predictable deployments.

---

## Final Thoughts

FastAPI Lifespan is more than a replacement for startup and shutdown events.

It provides a structured, context-manager-based approach for managing application resources throughout their entire lifecycle.

Whether you're initializing database pools, loading machine learning models, creating Redis connections, starting schedulers, or managing background workers, Lifespan gives you a single, predictable location to orchestrate those resources.

For modern FastAPI applications, Lifespan is no longer just the recommended pattern—it has effectively become the standard way to build production-grade startup and shutdown workflows.
