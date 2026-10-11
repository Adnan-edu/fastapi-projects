# FastAPI Performance: The 80/20 Guide to Profiling Async Services

Source article: [FastAPI Performance: Complete Guide to Profiling Async Services](https://medium.com/@rameshkannanyt0078/fastapi-performance-complete-guide-to-profiling-async-services-dc3e709488da)

## Assumption

This is an original learning note, not a reproduction of the Medium article. The article is member-only, so this guide uses the visible excerpt, the topic implied by the excerpt, and supporting web research from official or primary documentation.

## Core Idea

The `@app.get()` decorator registers a route; it does not make the code inside that route non-blocking. FastAPI performance depends on whether your whole request path yields control while waiting on I/O, whether you can see where time is being spent, and whether your database, thread pool, worker processes, and external dependencies can handle concurrent load.

## The Most Important Correction

The article's warning is directionally right: "async-looking" code can still behave like a slow sequential service. But the exact mechanics matter:

- `async def` route: FastAPI runs it on the event loop. If you call blocking code inside it, such as `requests.get()`, `time.sleep()`, a sync SQLAlchemy query, or a sync PostgreSQL driver like `psycopg2`, you block that worker's event loop.
- `def` route: FastAPI/Starlette runs it in a thread pool and awaits the result. The event loop is protected, but each slow blocking call consumes one thread-pool token and usually one database connection. Under load, the thread pool or DB pool can saturate and requests queue.
- `@app.get()` by itself changes neither of those facts. The function signature and the libraries you call are what matter.

So the better rule is:

> Use `async def` only when the work inside it is non-blocking or awaited. Keep sync code in `def` routes or deliberately move it to a thread, but do not mistake thread-pool concurrency for true async I/O.

## The 20% of Concepts That Explains 80% of FastAPI Performance Problems

| Concept | What It Means | Why It Matters |
| --- | --- | --- |
| ASGI server | Uvicorn or another ASGI server receives HTTP requests and calls your FastAPI app. | FastAPI itself is not the process manager or socket server. Worker count, reload mode, and deployment settings affect throughput. |
| Event loop | A single-threaded scheduler that runs async tasks until they hit an `await`. | One blocking call inside the loop can delay every other coroutine in that worker. |
| `async def` | A coroutine function. It can yield control only when it awaits awaitable, non-blocking work. | Declaring `async` does not magically make sync libraries non-blocking. |
| `def` route | A synchronous route that FastAPI runs in a thread pool. | It avoids blocking the event loop, but it can still queue when thread tokens or DB connections are exhausted. |
| Blocking I/O | Work that makes the current thread wait: sync DB drivers, sync HTTP clients, slow file reads, `time.sleep()`. | This is the usual reason "local is fast, production is slow." |
| Async I/O | I/O through awaitable libraries such as `httpx.AsyncClient`, async SQLAlchemy with an async driver, or other AnyIO/asyncio-compatible clients. | This lets one worker make progress on other requests while waiting on network or database responses. |
| Connection pool | A fixed set of reusable DB or HTTP connections. | Too small causes queuing; too large can overload the database. Pool size must match real concurrency. |
| Observability | Logs, metrics, and traces that explain behavior in production. | A `200 OK` log tells you almost nothing about where 8 seconds went. |
| Profiling | Measuring where CPU time, wall time, or blocking waits occur. | It prevents guessing. The bottleneck is often DB, serialization, hidden sync I/O, or external calls, not FastAPI itself. |
| Percentiles | p50, p95, p99 latency under load. | Average latency hides the user pain. Production performance is usually a tail-latency problem. |

## The Mental Model

FastAPI can handle many concurrent I/O-bound requests because async tasks cooperate:

1. A request enters an `async def` route.
2. The route starts a DB or HTTP operation and hits `await`.
3. The event loop pauses that coroutine.
4. The worker handles other requests while the first one waits.
5. When the I/O result is ready, the coroutine resumes.

That model breaks when a route says `async def` but calls blocking code:

```python
@app.get("/products/{sku}")
async def get_product(sku: str):
    # Bad inside async def: sync ORM/session/driver call.
    return db.query(Product).filter(Product.sku == sku).first()
```

The route is async, but the DB call is not. The event loop cannot switch to other work while that sync query waits.

If you cannot switch the DB stack yet, a sync route is often safer:

```python
@app.get("/products/{sku}")
def get_product(sku: str):
    # Runs in FastAPI/Starlette's thread pool.
    return db.query(Product).filter(Product.sku == sku).first()
```

This protects the event loop, but it is still limited by thread-pool capacity and DB pool capacity.

The fully async version requires the route and the data layer to be async:

```python
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/products/{sku}")
async def get_product(
    sku: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Product).where(Product.sku == sku)
    )
    return result.scalar_one_or_none()
```

For PostgreSQL, that usually means an async SQLAlchemy engine URL such as:

```text
postgresql+asyncpg://user:password@host/dbname
```

## The Performance Failure Modes to Recognize

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| One slow request makes many unrelated requests slow | Blocking code inside `async def` | Search for `requests`, `time.sleep`, sync ORM calls, CPU loops, sync file I/O inside async routes. |
| Latency jumps only under concurrency | Thread pool, DB pool, or external API saturation | Compare app concurrency, Starlette thread tokens, DB pool size, DB max connections, and upstream rate limits. |
| CPU is low but requests are slow | Waiting on DB, network, locks, or connection acquisition | Add spans/timers around DB queries and external calls. Check database slow-query logs. |
| CPU is high on one worker | CPU-bound code in the request path | Use `py-spy` or `pyinstrument`; move CPU work to a process pool or background worker. |
| Average latency seems fine but users complain | Bad p95/p99 latency | Track percentiles, not only averages. Load-test at realistic concurrency. |
| Localhost looks fast, production crawls | No production-like load or network conditions | Test with concurrency, real DB size, realistic indexes, and real external dependencies. |

## The Practical Profiling Ladder

Start with the least invasive tool that can answer the next question.

1. Request timing middleware

   Add request IDs and duration logs. This answers: "Which route is slow, how often, and for whom?"

```python
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)
app = FastAPI()

request_id_var: ContextVar[Optional[str]] = ContextVar(
    "request_id",
    default=None,
)

@app.middleware("http")
async def request_timing(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:8])
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        request_id_var.reset(token)
```

2. Span-level timers

   Add timers around the obvious expensive operations:

```python
start = time.perf_counter()
result = await session.execute(statement)
logger.info(
    "db_query_complete",
    extra={
        "request_id": request_id_var.get(),
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        "operation": "product_by_sku",
    },
)
```

3. Metrics

   Track request count, error count, in-flight requests, and latency histograms. The useful dashboard is usually:

- RPS: requests per second.
- Error rate: 4xx and 5xx split.
- Duration: p50, p95, p99 by route.
- Saturation: worker CPU, memory, thread-pool pressure, DB pool usage, DB CPU/locks.

4. Distributed tracing

   Use OpenTelemetry when a request crosses multiple layers or services. A trace should show:

```text
HTTP request
  -> auth dependency
  -> DB query: product_by_sku
  -> external inventory API
  -> serialization
```

5. Profilers

   Use profilers when logs and traces show that the app process itself is spending time somewhere unexpected.

- `pyinstrument`: good for local, wall-time profiling and readable call trees, including async programs.
- `py-spy`: good for attaching to a running process and generating flame graphs with low overhead.
- `cProfile`: built in, useful for deterministic function-call stats, but can be noisy for async web services.
- Python asyncio debug / slow callbacks: useful for detecting callbacks or tasks that hold the event loop too long.

Example production-safe starting point:

```bash
py-spy record -o profile.svg --pid <uvicorn_worker_pid>
```

## Techniques That Fix the Real Bottlenecks

### 1. Keep the stack consistently sync or consistently async

Good sync route:

```python
@app.get("/sync-products/{sku}")
def read_product(sku: str):
    return sync_repo.get_product(sku)
```

Good async route:

```python
@app.get("/async-products/{sku}")
async def read_product(sku: str):
    return await async_repo.get_product(sku)
```

Risky mixed route:

```python
@app.get("/mixed-products/{sku}")
async def read_product(sku: str):
    return sync_repo.get_product(sku)
```

### 2. Replace sync HTTP calls in async routes

Avoid this inside `async def`:

```python
import requests

response = requests.get(url, timeout=5)
```

Use this:

```python
import httpx

async with httpx.AsyncClient(timeout=5.0) as client:
    response = await client.get(url)
```

For hot paths, reuse a long-lived `AsyncClient` rather than creating a new client inside tight loops.

### 3. Use async database drivers only when the whole path supports async

For SQLAlchemy, use:

- `create_async_engine(...)`
- an async dialect such as `postgresql+asyncpg`
- `AsyncSession`
- `await session.execute(...)`

Do not assume that adding `await` around a sync DB call makes it async. It must be an awaitable API from an async-capable driver or library.

### 4. Tune pools with measurements

Important pools:

- Uvicorn/FastAPI workers: processes.
- Starlette/AnyIO thread pool: sync route/dependency capacity. Starlette's documented default is 40 tokens, shared by sync endpoints, sync dependencies, file responses, uploads, and some internal work.
- SQLAlchemy DB pool: database connections per process.
- HTTP client pool: outbound connection reuse.

More is not always better. A DB pool of 100 per worker across 8 workers can become 800 possible DB connections. That can make the database slower, not faster.

### 5. Move CPU-heavy or long-running work out of the request path

For short blocking I/O that you cannot replace yet:

```python
import asyncio

result = await asyncio.to_thread(sync_io_function, arg1, arg2)
```

For CPU-bound work or long jobs, prefer a process pool or a real worker queue such as Celery, RQ, Dramatiq, or a platform-native job system. Threads do not give reliable parallel CPU execution for normal Python bytecode because of the GIL.

### 6. Add timeouts and backpressure

Every external dependency should have:

- connect timeout
- read timeout
- retry policy only when safe
- concurrency limit or semaphore when the upstream cannot handle unlimited parallel calls
- clear fallback or error behavior

Without timeouts, one slow dependency can consume all request capacity.

## The 80/20 Glossary

- ASGI: The async interface between Uvicorn and FastAPI.
- Uvicorn worker: A process running your app and its own event loop.
- Event loop: The scheduler for async tasks inside one worker.
- Coroutine: The object produced by calling an `async def` function.
- Awaitable: Something that can be used with `await`.
- Blocking call: A call that stops the current thread until it finishes.
- Thread pool: A group of threads used to run sync functions without blocking the event loop.
- Thread-pool token: Starlette/AnyIO's capacity unit for concurrent sync work.
- Connection pool: A reusable set of DB or HTTP connections.
- Span: One timed operation inside a trace.
- Trace: The full path of one request across operations or services.
- Metric: A numeric measurement over time, such as latency or error count.
- Flame graph: A profiler visualization showing where runtime is spent.
- p95/p99: Tail latency percentiles. p99 means 99% of requests were faster and 1% were slower.

## Three Simple, Actionable Steps

### Step 1: Add visibility before changing code

Add request timing middleware today. Log `request_id`, route, status code, and duration. Then add one timer around the slowest DB query or external API call. The goal is to answer: "Where did this request spend its time?"

Immediate checklist:

- Add `x-request-id` to every response.
- Log route duration with `time.perf_counter()`.
- Add one DB or HTTP client timer in the suspected slow endpoint.
- Track p95 and p99 latency, not only averages.

### Step 2: Audit one slow endpoint for hidden blocking

Pick the endpoint you care about most and search its call path for:

```text
requests.
time.sleep(
subprocess.run(
open(
db.query(
Session(
psycopg2
```

Then choose one path:

- If the stack is sync, keep the route as `def`, size the thread pool and DB pool, and avoid pretending it is async.
- If the stack should be async, convert the whole path: route, repository, DB session, driver, HTTP client, and tests.

Do not only change `def` to `async def`. That is the classic trap.

### Step 3: Run a small load test and profile the bottleneck

Run the endpoint at realistic concurrency, even for 30 seconds:

```bash
hey -z 30s -c 50 http://localhost:8000/products/ABC123
```

During the run:

- Watch p50, p95, p99, and error rate.
- Check DB slow-query logs or query plans.
- Attach `py-spy` to the busiest worker if app CPU looks suspicious.
- Fix only the top bottleneck, then repeat the same test.

This loop is the habit that matters: measure, change one thing, measure again.

## Sources Researched

- Medium excerpt: [FastAPI Performance: Complete Guide to Profiling Async Services](https://medium.com/@rameshkannanyt0078/fastapi-performance-complete-guide-to-profiling-async-services-dc3e709488da)
- FastAPI docs: [Concurrency and async / await](https://fastapi.tiangolo.com/async/)
- FastAPI docs: [Server Workers - Uvicorn with Workers](https://fastapi.tiangolo.com/deployment/server-workers/)
- Starlette docs: [Thread Pool](https://starlette.dev/threadpool/)
- SQLAlchemy docs: [Asynchronous I/O](https://docs.sqlalchemy.org/20/orm/extensions/asyncio.html)
- HTTPX docs: [Async Support](https://www.python-httpx.org/async/)
- OpenTelemetry docs: [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- OpenTelemetry Python Contrib: [FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
- Python docs: [asyncio event loop and slow callbacks](https://docs.python.org/3/library/asyncio-eventloop.html)
- Python docs: [asyncio.to_thread](https://docs.python.org/3.10/library/asyncio-task.html#asyncio.to_thread)
- Pyinstrument docs: [How it works](https://pyinstrument.readthedocs.io/en/latest/how-it-works.html)
- py-spy guide: [Profiling a Python script with py-spy](https://pydevtools.com/handbook/how-to/how-to-profile-a-python-script-with-py-spy/)
