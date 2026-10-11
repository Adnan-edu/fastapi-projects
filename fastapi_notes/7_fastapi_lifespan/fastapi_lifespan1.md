I'll now complete your article with comprehensive, production-ready content about FastAPI Lifespan. Based on my research, here's the full article:

----

Every serious backend application has work that must happen before it starts serving requests — and just as important, work that must happen after it stops.

Database connections need to be initialized.
Schemas and tables must exist.
Background resources must be cleaned up properly.

In FastAPI, the modern and recommended way to manage this lifecycle logic is the Lifespan feature.

This article explains what FastAPI Lifespan is, why it replaced older patterns, and how to use it correctly in production‑ready applications.

## What Is FastAPI Lifespan?

FastAPI Lifespan is a mechanism that lets you define:

- **Startup logic** (runs when the app starts)
- **Shutdown logic** (runs when the app stops)

It replaces the older:

```python
@app.on_event("startup")
@app.on_event("shutdown")
```

These decorators are now **deprecated** (since FastAPI 0.95.0). The new lifespan API offers a cleaner, more flexible approach using async context managers. [dev.turmansolutions](https://dev.turmansolutions.ai/2025/09/27/understanding-fastapis-lifespan-events-proper-initialization-and-shutdown/)

## Why Lifespan Replaced `@app.on_event`

| Aspect | Old `@app.on_event` | New `lifespan` |
|--------|---------------------|----------------|
| **Structure** | Separate functions for startup/shutdown | Single function with `yield` |
| **Shared state** | Requires global variables | Clean state via `app.state` |
| **Async support** | Mixed sync/async confusion | Proper async context manager |
| **Resource pairing** | Hard to connect init/cleanup | Code before/after `yield` naturally paired |
| **Testing** | Works with `TestClient` | Requires `with TestClient(app)`  [fastapi.tiangolo](https://fastapi.tiangolo.com/advanced/testing-events/) |

**Important:** If you provide a `lifespan` parameter, `startup` and `shutdown` event handlers will **no longer be called**. It's all lifespan OR all events, not both. [fastapi.tiangolo](https://fastapi.tiangolo.com/advanced/events/)

## Basic Lifespan Syntax

Here's the fundamental pattern:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic (before yield)
    print("App is starting...")
    
    yield
    
    # Shutdown logic (after yield)
    print("App is shutting down...")

app = FastAPI(lifespan=lifespan)
```

The code **before** `yield` runs once at startup. The code **after** `yield` runs once at shutdown. [learn.xtec](https://learn.xtec.dev/python/fastapi/lifespan)

## Production Example: Database Connection Pool

This is the most common use case. Here's a complete SQLAlchemy async example:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/dbname"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create engine and connection pool
    app.state.engine = create_async_engine(DATABASE_URL, echo=True)
    app.state.SessionLocal = sessionmaker(
        app.state.engine, 
        class_=AsyncSession, 
        expire_on_commit=False
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
    # Use db session here
    return {"message": "Items retrieved"}
```

This ensures the database pool is created **once** at startup and properly disposed at shutdown. [vskills](https://www.vskills.in/certification/tutorial/database-connections-using-lifespan-events-in-fastapi/)

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



## Production Example: Background Tasks

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from asyncio import create_task, Task

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    job: Task = create_task(periodic_job())
    
    yield
    
    # Cancel background task on shutdown
    job.cancel()
    try:
        await job
    except asyncio.CancelledError:
        pass

async def periodic_job():
    while True:
        print("Job running...")
        await asyncio.sleep(10)

app = FastAPI(lifespan=lifespan)
```



## Production Example: ML Model Loading

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load expensive ML model once at startup
    print("Loading ML model...")
    app.state.model = load_model()  # Takes several seconds
    print("Model loaded!")
    
    yield
    
    # Free GPU/memory on shutdown
    del app.state.model
    import gc
    gc.collect()

def load_model():
    # Simulate expensive load
    import time
    time.sleep(3)
    return "mock_model"

@app.get("/predict")
async def predict(x: float):
    result = app.state.model.predict(x)
    return {"result": result}

app = FastAPI(lifespan=lifespan)
```

This avoids loading the model on every request and ensures proper cleanup. [fastapi.tiangolo](https://fastapi.tiangolo.com/advanced/events/)

## Testing Lifespan with TestClient

**Critical:** When testing, you must use `with TestClient(app)` to trigger lifespan events:

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



## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| **Accessing `app.state` before initialization** | Only access `app.state.X` after startup, inside routes |
| **Using sync code in async lifespan** | Use `async def` and `await` for non-blocking I/O  [dev.turmansolutions](https://dev.turmansolutions.ai/2025/09/27/understanding-fastapis-lifespan-events-proper-initialization-and-shutdown/) |
| **Not testing with `with TestClient()`** | Lifespan won't run in tests without the context manager  [fastapi.tiangolo](https://fastapi.tiangolo.com/ja/advanced/testing-events/) |
| **Mixing lifespan + `@app.on_event`** | Use one or the other, not both  [fastapi.tiangolo](https://fastapi.tiangolo.com/advanced/events/) |
| **Sub-applications** | Lifespan only runs for the **main** app, not mounts  [scribd](https://www.scribd.com/document/833894657/FastAPI-Lifespan-Events) |

## Best Practices for Production

1. **Centralize all initialization** in the lifespan function instead of global scope code [dev.turmansolutions](https://dev.turmansolutions.ai/2025/09/27/understanding-fastapis-lifespan-events-proper-initialization-and-shutdown/)

2. **Wrap third-party async resources** inside lifespan for portability and testability [dev.turmansolutions](https://dev.turmansolutions.ai/2025/09/27/understanding-fastapis-lifespan-events-proper-initialization-and-shutdown/)

3. **Add health checks** after startup to verify resources are ready:
   ```python
   @app.get("/health")
   async def health_check():
       await app.state.engine.execute("SELECT 1")
       return {"status": "healthy"}
   ```

4. **Use dedicated utility classes** for complex initialization:
   ```python
   class DatabaseUtility:
       @staticmethod
       async def initialize(): ...
       @staticmethod
       async def shutdown(): ...
   
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       await DatabaseUtility.initialize()
       yield
       await DatabaseUtility.shutdown()
   ```
 [linkedin](https://www.linkedin.com/pulse/fastapi-playbook-best-practices-chapter-3-sourav-aggarwal-ltf1c)

5. **Log startup/shutdown** for observability:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       logger.info("Application starting up")
       yield
       logger.info("Application shutting down")
   ```
 [dev](https://dev.to/lisan_al_gaib/building-a-health-check-microservice-with-fastapi-26jo)

## Summary

FastAPI Lifespan is the **modern, recommended** way to handle startup and shutdown logic. It replaces deprecated `@app.on_event` decorators with a single async context manager that:

- Guarantees proper async resource management
- Pairs initialization and cleanup naturally
- Enables clean shared state via `app.state`
- Works seamlessly with testing when using `with TestClient(app)`

For any production FastAPI application managing database connections, background tasks, ML models, or external services, **use lifespan** — your future self (and your deployments) will thank you. [linkedin](https://www.linkedin.com/pulse/fastapi-playbook-best-practices-chapter-3-sourav-aggarwal-ltf1c)

----

This completes your article with deep research covering:
- Core concepts and motivation
- Basic and advanced code examples (database, MongoDB, background tasks, ML models)
- Testing patterns
- Common pitfalls in a table format
- Production best practices
- All properly cited from FastAPI official docs and expert sources