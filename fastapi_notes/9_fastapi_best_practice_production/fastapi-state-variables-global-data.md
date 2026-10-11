# FastAPI State Variables Explained: The 80/20 Guide to Sharing Global Data Safely

## Purpose

This note explains the most important 20% of FastAPI state management that will help you understand 80% of real-world use cases: how to share application-wide resources, how to attach request-specific metadata, when to use `contextvars`, and how to avoid the usual production traps.

It merges the ideas from the pasted article draft with current FastAPI, Starlette, HTTPX, Pydantic, and Python documentation. It is an original learning guide, not a copy of any single source.

## The Core Idea

FastAPI apps often need shared objects:

- a database engine or connection pool
- a Redis client
- an `httpx.AsyncClient`
- a loaded machine learning model
- a feature flag client
- a telemetry or metrics client

The mistake is to create those objects as casual module-level globals and hope they behave well under concurrency, testing, reloads, and shutdown.

The better mental model is:

> Put long-lived resources in the application lifespan. Put per-request metadata on `request.state`. Use dependency functions as adapters so route handlers ask for what they need without knowing where it is stored.

## The Most Important Correction

`app.state` and `request.state` are storage namespaces. They do not make the objects inside them safe.

If you put a mutable dictionary in state and update it from multiple requests, workers, or threads, FastAPI does not automatically protect it. If you run multiple Uvicorn workers, each worker process has its own independent memory and therefore its own independent app state.

So this is fine as a toy demo:

```python
app.state.counter = {"total": 0}
```

But this is not a reliable production-wide counter:

```python
app.state.counter["total"] += 1
```

For real production counters, use a metrics system, Redis, a database, or another shared external store. For an in-process demo counter, protect mutation with a lock and remember it is still per process.

## The 20% of Concepts That Gives You 80% of the Understanding

| Concept | What It Means | Use It For | Avoid Using It For |
| --- | --- | --- | --- |
| Lifespan | Startup and shutdown context for the app. Code before `yield` runs before serving; code after `yield` runs during shutdown. | Creating and closing DB pools, HTTP clients, Redis clients, ML models. | Per-request work. |
| `app.state` | A dynamic namespace attached to the application object. | App-wide resources assigned during lifespan, especially with `request.app.state`. | Static config, uncontrolled mutable globals, cross-worker counters. |
| Lifespan state | In current Starlette/FastAPI stacks, lifespan can `yield` a dictionary that becomes available on `request.state` as a shallow copy. | Typed resource access with `Request[State]` and `request.state["key"]`. | Older Starlette versions unless you verify support. |
| `request.state` | A dynamic namespace attached to one request. | Correlation IDs, decoded auth payloads, timing markers, tenant IDs. | Anything that should outlive the request. |
| Dependency adapter | A small `Depends` function that reads state and returns a resource. | Decoupling endpoints from `request.app.state` or `request.state`. | Hiding expensive work that should be in lifespan. |
| `contextvars` | Python task-local context storage. | Deep logging/tracing context when passing `Request` everywhere would be ugly. | General request state, especially when sync code runs in a thread pool. |
| Pydantic Settings | Typed configuration loaded from env vars or `.env` files. | API keys, URLs, feature flags, timeouts, environment names. | Live clients, connection pools, mutable runtime resources. |
| Worker process | One running app process, usually one Uvicorn worker. | Parallelizing across CPU cores. | Assuming memory is shared between workers. |

## Decision Rule

Use this quick rule before storing anything:

| Question | Best Place |
| --- | --- |
| Is it static configuration from environment variables? | Pydantic Settings |
| Is it expensive to create and reused across requests? | Lifespan-managed app resource |
| Does it need cleanup on shutdown? | Lifespan-managed app resource |
| Is it only true for this one HTTP request? | `request.state` |
| Is it needed deep in logging/tracing without passing parameters? | `contextvars`, carefully |
| Must it be shared across multiple workers or machines? | External store, not in-memory state |

## Lifespan Is the Modern Startup/Shutdown Pattern

FastAPI still has examples of startup and shutdown events, but the recommended modern pattern is the `lifespan` parameter. FastAPI documents `@app.on_event("startup")` and `@app.on_event("shutdown")` as the alternative events pattern, and marks it deprecated in the API reference. If you provide a `lifespan`, startup/shutdown event handlers are not called. It is one style or the other.

The lifespan pattern is better because resource creation and cleanup live in the same function:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

Everything before `yield` is startup. Everything after `yield` is shutdown. This is ideal for resources that should be created once per worker process and closed cleanly.

## Two Valid Ways to Share App Resources

There are two common patterns. Pick one and use it consistently.

### Pattern A: Store Resources on `app.state`

This is simple and works broadly:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        app.state.http_client = client
        yield

app = FastAPI(lifespan=lifespan)

def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client

HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]

@app.get("/status")
async def status(client: HttpClient) -> dict[str, int]:
    response = await client.get("https://httpbin.org/status/204")
    return {"external_status": response.status_code}
```

Why this is good:

- `httpx.AsyncClient` is created once per worker, not once per request.
- The client is closed during shutdown.
- Endpoints depend on `HttpClient`, not on `app.state` directly.
- Tests can override `get_http_client`.

### Pattern B: Yield Typed Lifespan State

Current Starlette documentation also supports returning state from the lifespan handler. That state is available on requests through `request.state`. The request receives a shallow copy of the lifespan state dictionary, so the dictionary container is copied but the stored resource objects are the same objects.

Starlette 0.52.0 introduced dictionary-style state access and generic `Request[State]` typing for better type checking. If your installed Starlette version is older, use Pattern A or attribute access instead.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, TypedDict

import httpx
from fastapi import Depends, FastAPI
from starlette.requests import Request

class AppState(TypedDict):
    http_client: httpx.AsyncClient

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[AppState]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        yield {"http_client": client}

app = FastAPI(lifespan=lifespan)

def get_http_client(request: Request[AppState]) -> httpx.AsyncClient:
    return request.state["http_client"]

HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]

@app.get("/status")
async def status(client: HttpClient) -> dict[str, int]:
    response = await client.get("https://httpbin.org/status/204")
    return {"external_status": response.status_code}
```

Why this is good:

- `TypedDict` gives static type checkers a known state shape.
- `request.state["http_client"]` can reveal the exact type in compatible Starlette versions.
- The lifecycle is still owned by lifespan.

## `request.state` Is for One Request Only

Use `request.state` when middleware or dependencies need to attach information that belongs only to the current HTTP request.

Good examples:

- correlation ID
- request start time
- decoded user claims
- tenant ID
- audit context
- request-specific permission result

Example middleware:

```python
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

app = FastAPI()

@app.middleware("http")
async def add_request_context(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    correlation_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    request.state.correlation_id = correlation_id
    request.state.started_at = time.perf_counter()

    response = await call_next(request)

    response.headers["x-correlation-id"] = correlation_id
    response.headers["x-process-time-ms"] = str(
        round((time.perf_counter() - request.state.started_at) * 1000, 2)
    )
    return response
```

Important fix from the pasted draft: set a specific header key:

```python
response.headers["x-correlation-id"] = correlation_id
```

Do not do this:

```python
response.headers = correlation_id
```

`response.headers` is a headers mapping, not a string field.

## Dependency Adapters Keep Endpoints Clean

Directly writing `request.app.state.http_client` in every endpoint works, but it spreads framework plumbing everywhere. A small dependency adapter gives you cleaner endpoints and easier tests.

Instead of this:

```python
@app.get("/items")
async def items(request: Request):
    client = request.app.state.http_client
    ...
```

Prefer this:

```python
from typing import Annotated

import httpx
from fastapi import Depends, Request

def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client

HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]

@app.get("/items")
async def items(client: HttpClient):
    ...
```

This gives you one small place to change how the resource is found, and it lets tests override the dependency:

```python
app.dependency_overrides[get_http_client] = lambda: fake_client
```

## `contextvars`: Powerful, But Not the Default State Tool

Python `contextvars` provide context-local state. They are useful when you want request context available deep inside code without passing `request` through every function. Logging correlation IDs are a common example.

Example:

```python
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)
```

Middleware can set it:

```python
token = correlation_id_var.set(correlation_id)
try:
    response = await call_next(request)
finally:
    correlation_id_var.reset(token)
```

Then a logging helper can read it:

```python
cid = correlation_id_var.get()
```

The catch: context variables work naturally with asyncio task-local context, but sync endpoints and sync dependencies may run in a thread pool. The current context may be copied into the worker thread, but changes made inside that worker thread do not reliably propagate back to the async caller. This is why `contextvars` are excellent for logging context set by middleware, but they are not a replacement for `request.state` as a general request data bus.

Use this rule:

- Use `request.state` when request data must be passed through the FastAPI request pipeline.
- Use `contextvars` when deep library code needs read-only contextual information such as a correlation ID.
- Avoid setting important request state inside sync thread-pool code and expecting middleware to see the changed value later.

## Configuration Is Not Live State

Do not use `app.state` as a dumping ground for static config:

```python
app.state.database_url = "postgresql://..."
app.state.api_key = "..."
```

Use Pydantic Settings for config:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "State Demo API"
    external_api_base_url: str
    external_api_timeout_seconds: float = 10.0

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Then use those settings to create live resources during lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.external_api_base_url,
        timeout=settings.external_api_timeout_seconds,
    ) as client:
        app.state.http_client = client
        yield
```

Clean separation:

- Settings: validated static configuration.
- Lifespan: live resource creation and cleanup.
- State: access to those live resources during requests.

## A Corrected Mini Architecture

The pasted draft used an async HTTP client and a request counter. The HTTP client is a good state example. The in-memory counter is fine for demonstration, but production counters should usually be external metrics.

This version keeps the example honest:

- `http_client` is a lifespan-managed app resource.
- `RequestCounter` is in-process only and protected by a lock.
- `correlation_id` is request-scoped.
- endpoints receive resources through dependencies.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
import asyncio
import time
import uuid

import httpx
from fastapi import Depends, FastAPI, Request, Response

class RequestCounter:
    def __init__(self) -> None:
        self._total = 0
        self._lock = asyncio.Lock()

    async def increment(self) -> int:
        async with self._lock:
            self._total += 1
            return self._total

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
        timeout=httpx.Timeout(10.0),
    ) as client:
        app.state.http_client = client
        app.state.request_counter = RequestCounter()
        yield

app = FastAPI(title="State Demo API", lifespan=lifespan)

def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client

def get_request_counter(request: Request) -> RequestCounter:
    return request.app.state.request_counter

HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
Counter = Annotated[RequestCounter, Depends(get_request_counter)]

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    request.state.correlation_id = correlation_id
    request.state.started_at = time.perf_counter()

    response: Response = await call_next(request)

    response.headers["x-correlation-id"] = correlation_id
    response.headers["x-process-time-ms"] = str(
        round((time.perf_counter() - request.state.started_at) * 1000, 2)
    )
    return response

@app.get("/external-query")
async def execute_external_query(
    request: Request,
    client: HttpClient,
    counter: Counter,
) -> dict[str, int | str]:
    total = await counter.increment()
    response = await client.get("https://httpbin.org/status/200")

    return {
        "correlation_id": request.state.correlation_id,
        "in_process_request_count": total,
        "external_status": response.status_code,
    }
```

Production warning:

If you run this with `uvicorn main:app --workers 4`, each worker has its own `RequestCounter`. The values are not shared across workers. That is correct for app memory, but wrong for global business counters.

## Common Mistakes and Fixes

| Mistake | Why It Hurts | Better Approach |
| --- | --- | --- |
| Creating `httpx.AsyncClient()` inside every request | Loses connection pooling and can leak resources if not closed. | Create once in lifespan and close on shutdown. |
| Using module-level clients | Harder tests, awkward shutdown, surprises with reload/workers. | Create clients in lifespan. |
| Putting secrets and URLs in `app.state` | No validation, unclear ownership. | Use Pydantic Settings. |
| Updating a global dict as a production counter | Not cross-process and not automatically concurrency-safe. | Use metrics, Redis, DB, or a lock-protected in-process demo only. |
| Passing `Request` deep into business logic | Couples domain code to FastAPI/Starlette. | Use dependency adapters and pass plain resources/services. |
| Expecting `contextvars` to behave like universal request globals | Sync thread-pool boundaries can break back-propagation. | Use `request.state` for request data; use `contextvars` mainly for logging/tracing context. |
| Mixing `lifespan` and `@app.on_event` | FastAPI says it is all lifespan or all events. | Prefer lifespan for new code. |
| Assuming `app.state` is shared by all Uvicorn workers | Each worker is a process with separate memory. | Use external stores for shared state. |

## How to Test State Correctly

Use the test client as a context manager so lifespan startup and shutdown run:

```python
from fastapi.testclient import TestClient

def test_external_query():
    with TestClient(app) as client:
        response = client.get("/external-query")
        assert response.status_code == 200
        assert "x-correlation-id" in response.headers
```

Override dependency adapters instead of reaching into internals:

```python
class FakeClient:
    async def get(self, url: str):
        class Response:
            status_code = 200

        return Response()

app.dependency_overrides[get_http_client] = lambda: FakeClient()
```

After the test, clear overrides:

```python
app.dependency_overrides.clear()
```

## Three Simple, Actionable Steps

### Step 1: Classify Your State

Open one FastAPI project and list every global-ish thing:

```text
database URL
database engine
Redis client
HTTP client
JWT secret
current user
correlation ID
request start time
ML model
counter
```

Then classify each one:

- Config: move to Pydantic Settings.
- Long-lived resource: initialize in lifespan.
- Request-only metadata: attach to `request.state`.
- Cross-worker shared value: move to Redis, DB, or metrics.
- Logging-only context: consider `contextvars`.

### Step 2: Wrap App State with Dependencies

Pick one shared resource and hide state access behind one dependency:

```python
def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client
```

Then update endpoints to request the resource:

```python
HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]

@app.get("/example")
async def example(client: HttpClient):
    ...
```

This one move makes the code easier to test and easier to refactor later.

### Step 3: Add Request Context Middleware

Add a correlation ID and duration timer:

```python
@app.middleware("http")
async def add_request_context(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    request.state.correlation_id = correlation_id
    request.state.started_at = time.perf_counter()

    response = await call_next(request)

    response.headers["x-correlation-id"] = correlation_id
    response.headers["x-process-time-ms"] = str(
        round((time.perf_counter() - request.state.started_at) * 1000, 2)
    )
    return response
```

Now every request has a traceable ID, and every response carries timing information you can inspect immediately.

## Quick Reference

| Need | Recommended Tool |
| --- | --- |
| Load a model once | Lifespan |
| Open and close an HTTP client | Lifespan |
| Open and close a DB engine/pool | Lifespan |
| Access a shared client in routes | Dependency adapter |
| Add correlation ID | `request.state` in middleware |
| Read current correlation ID in logging helper | `contextvars` |
| Store API key or DB URL | Pydantic Settings |
| Count requests across all workers | Metrics backend, Redis, or database |
| Type-check state | `TypedDict` plus Starlette `Request[State]` when supported |

## Final Mental Model

Think in lifetimes:

```text
Environment / deployment
  -> Pydantic Settings

Application worker lifetime
  -> lifespan
  -> app.state or lifespan state
  -> shared clients, pools, models

Single request lifetime
  -> request.state
  -> correlation ID, user context, timing

Deep async call chain
  -> contextvars
  -> logging/tracing context
```

If you get the lifetime right, the storage mechanism usually becomes obvious.

## Sources Researched

- [FastAPI: Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI: Using the Request Directly](https://fastapi.tiangolo.com/advanced/using-request-directly/)
- [FastAPI: Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [FastAPI: Testing Dependencies with Overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [FastAPI: Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- [FastAPI: Server Workers - Uvicorn with Workers](https://fastapi.tiangolo.com/deployment/server-workers/)
- [Starlette: Applications and app.state](https://starlette.dev/applications/)
- [Starlette: Lifespan and lifespan state](https://starlette.dev/lifespan/)
- [Starlette: Requests and request.state](https://starlette.dev/requests/)
- [Starlette: Thread Pool](https://www.starlette.io/threadpool/)
- [HTTPX: Async Support](https://www.python-httpx.org/async/)
- [HTTPX: Resource Limits](https://www.python-httpx.org/advanced/resource-limits/)
- [Pydantic: Settings Management](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
- [Python docs: contextvars](https://docs.python.org/3/library/contextvars.html)
- [Python.org Async-SIG: back-propagation of contextvar changes from worker threads](https://discuss.python.org/t/back-propagation-of-contextvar-changes-from-worker-threads/15928)

## Implementation Roadmap: Three Actionable Steps to Production Readiness

This section details how to implement a type-safe, lifespan-managed state sharing architecture using a global request counter and an asynchronous HTTP client as shared resources.

The diagram below illustrates the flow of a request through this architecture, showing how middleware captures metrics and how dependency injection cleanly exposes stateful singletons to endpoints.

```text
Incoming Request
       |
       v
+--------------------------------------------------------+
|  Middleware: request.state.correlation_id = uuid4()    |  <-- Request-scoped
+--------------------------------------------------------+
       |
       v
+--------------------------------------------------------+
|  Route Handler Endpoint                                |
|  - Reads state via: Depends(get_http_client)           |  <-- App-scoped (Lifespan)
|  - Reads state via: Depends(get_request_counter)       |  <-- App-scoped (Lifespan)
+--------------------------------------------------------+
       |
       v
Outbound Response
```

### Step 1: Establish the Strongly-Typed State Contract

First, define the structures for both the application-scoped state and the request-scoped metadata. This setup ensures static type checkers can validate state interactions throughout the codebase.

```python
# app/state_contracts.py
from typing import TypedDict
import httpx

class GlobalStateSchema(TypedDict):
    """
    Contract for application-scoped resources initialized during
    the application lifespan and preserved across all requests.
    """
    http_client: httpx.AsyncClient
    request_counter: dict[str, int]


class RequestContextSchema(TypedDict):
    """
    Contract for temporary metadata attached to a single HTTP
    request, primarily populated by middleware.
    """
    correlation_id: str
```

### Step 2: Implement the Lifespan Context Manager

Next, write the lifespan context manager using the `@asynccontextmanager` decorator. This manager initializes the global state resources before the server starts accepting requests, yields them to the application, and ensures they are cleanly torn down upon shutdown.

```python
# app/lifespan_manager.py
from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
import httpx
from app.state_contracts import GlobalStateSchema

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    """
    Manages the lifecycle of global application state resources.
    Initializes singletons on startup and guarantees cleanup on shutdown.
    """
    # Startup Phase: Initialize shared resources
    client_pool = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
        timeout=httpx.Timeout(10.0)
    )

    # Initialize a simple in-memory request counter dictionary
    counter_store: dict[str, int] = {"total_processed": 0}

    # Pack resources into the typed state payload
    state_payload: GlobalStateSchema = {
        "http_client": client_pool,
        "request_counter": counter_store
    }

    # Yield control back to the FastAPI framework
    yield state_payload

    # Shutdown Phase: Safely close resources
    await client_pool.aclose()
```

### Step 3: Register Lifespan, Middleware, and Dependency Adapters

To complete the setup, define dependency functions that extract resources from the state. Then, instantiate the FastAPI application with the lifespan manager, add middleware to populate the request-scoped context, and inject the state dependencies into your endpoints.

```python
# app/main.py
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response, Depends
import httpx
from app.state_contracts import GlobalStateSchema, RequestContextSchema
from app.lifespan_manager import lifespan

# Instantiate the main application with the lifespan manager
app = FastAPI(title="TypeSafeStateAPI", lifespan=lifespan)

# Define clean dependency adapters to extract state from the request
def get_http_client(request: Request) -> httpx.AsyncClient:
    """
    Extracts the global asynchronous HTTP client from application state.
    """
    return request.state["http_client"]


def get_request_counter(request: Request) -> dict[str, int]:
    """
    Extracts the global request counter dictionary from application state.
    """
    return request.state["request_counter"]


# Middleware to initialize and populate request-scoped metadata
@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next: Callable
) -> Response:
    """
    Populates request.state with a correlation ID for tracing.
    """
    # Initialize the request context
    context: RequestContextSchema = {
        "correlation_id": str(uuid.uuid4())
    }
    request.state.context = context

    # Process the downstream pipeline
    response: Response = await call_next(request)

    # Append the correlation ID to outbound response headers
    response.headers["x-correlation-id"] = context["correlation_id"]
    return response


# Path operation leveraging dependency injection for global resources
@app.get("/external-query")
async def execute_external_query(
    request: Request,
    client: httpx.AsyncClient = Depends(get_http_client),
    counter: dict[str, int] = Depends(get_request_counter)
) -> dict:
    """
    Consumes the HTTP client and request counter singletons.
    Accesses request-scoped context via the middleware-populated state.
    """
    # Increment the global request counter
    counter["total_processed"] += 1

    # Retrieve the correlation ID from the request-scoped context
    req_context: RequestContextSchema = request.state.context
    cid = req_context["correlation_id"]

    # Execute an external request using the shared client connection pool
    response = await client.get("https://httpbin.org/delay/1")

    return {
        "correlation_id": cid,
        "global_request_count": counter["total_processed"],
        "external_status": response.status_code
    }
```
