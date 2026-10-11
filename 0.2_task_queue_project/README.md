# ARQ Task Queue Project

A production-grade FastAPI application that demonstrates **ARQ** (async Redis queue) integration with both **monolithic** and **microservice** deployment patterns. This project covers every major ARQ feature through real, runnable code across 15+ background tasks, 5 API routers, and 50 passing tests.

---

## Table of Contents

1. [What is ARQ?](#1-what-is-arq)
2. [Project Overview](#2-project-overview)
3. [Architecture Diagrams](#3-architecture-diagrams)
4. [Directory Structure](#4-directory-structure)
5. [Step 1: Foundation - Config and Database](#5-step-1-foundation---config-and-database)
6. [Step 2: Data Models and Schemas](#6-step-2-data-models-and-schemas)
7. [Step 3: ARQ Task Definitions](#7-step-3-arq-task-definitions)
8. [Step 4: The Worker - ARQ's Engine](#8-step-4-the-worker---arqs-engine)
9. [Step 5: Service Layer](#9-step-5-service-layer)
10. [Step 6: API Routes - Enqueue and Poll](#10-step-6-api-routes---enqueue-and-poll)
11. [Step 7: FastAPI Application with Lifespan](#11-step-7-fastapi-application-with-lifespan)
12. [Step 8: Docker Deployment](#12-step-8-docker-deployment)
13. [Step 9: Testing](#13-step-9-testing)
14. [ARQ Feature Reference](#14-arq-feature-reference)
15. [Running the Project](#15-running-the-project)
16. [Appendix A: End-to-End Stage Walkthrough](#16-appendix-a-end-to-end-stage-walkthrough)
17. [Appendix B: File-by-File Reading Guide](#17-appendix-b-file-by-file-reading-guide)
18. [Appendix C: Glossary of ARQ Terms](#18-appendix-c-glossary-of-arq-terms)
19. [Appendix D: Frequently Asked Questions](#19-appendix-d-frequently-asked-questions)

---

## 1. What is ARQ?

**ARQ** is a lightweight Python job queue built on top of **asyncio** and **Redis**. It is the async successor to RQ (Redis Queue) and provides:

- **Background job processing** - Offload slow work (email, reports, payments) from your API
- **Job uniqueness** - Prevent duplicate work with `_job_id`
- **Deferred execution** - Schedule jobs for the future with `_defer_by` or `_defer_until`
- **Retry with backoff** - Automatically retry failed jobs with exponential backoff
- **Cron scheduling** - Run recurring tasks on a schedule
- **Task chaining** - One task can enqueue another
- **Fan-out** - One task triggers many parallel sub-tasks
- **Health checks** - Monitor worker health via Redis keys
- **Queue isolation** - Separate workers for separate domains (microservice pattern)

The core idea: Your FastAPI app **enqueues** a job via Redis, and a separate **worker process** picks it up and executes it asynchronously.

```
FastAPI Request                   ARQ Worker
     |                                |
     |  redis.enqueue_job()           |
     |------------------------------> |
     |         Redis Queue            |
     |                                |
     |  (returns job_id immediately)  |  (picks up job)
     |                                |
     |                           Executes task function
     |                           Stores result in Redis
     |                                |
     |  job.result(timeout=5)         |
     |<------------------------------ |
```

---

## 2. Project Overview

This project is a **task queue API** that processes background work for multiple domains:

| Domain | Tasks | ARQ Features |
|--------|-------|-------------|
| **Email** | `send_welcome_email`, `send_report_email`, `send_batch_email` | Basic enqueue, `_job_id` dedup, fan-out |
| **Image** | `generate_thumbnail`, `resize_image` | `Retry` with backoff, `func()` per-task config |
| **Report** | `generate_pdf_report`, `generate_csv_export` | Task chaining (`_defer_by`), long timeout via `func()` |
| **Payment** | `process_payment`, `process_refund` | `_job_id` idempotency, `Retry` with backoff, `_defer_until` |
| **ETL** | `run_data_pipeline`, `sync_external_data` | `Retry` exponential backoff, `on_startup` resources |
| **Webhook** | `dispatch_webhook`, `retry_webhook` | `Retry` with backoff, `_job_id` uniqueness |
| **Notification** | `send_push_notification`, `batch_notify` | Fire-and-forget, fan-out pattern |
| **Cleanup** | `cleanup_expired_sessions`, `cleanup_old_job_results` | `@cron` with `run_at_startup`, `unique=True` |

The project supports two deployment modes:
- **Monolithic**: One API server + one worker running all tasks (`WorkerSettings`)
- **Microservice**: Separate workers per domain, each with its own `queue_name` (`WorkerSettingsEmail`, `WorkerSettingsPayment`, `WorkerSettingsReport`)

---

## 3. Architecture Diagrams

### Monolithic Mode

```
                    +-----------+
                    |  Redis    |
                    |  :6379    |
                    +-----+-----+
                          |
              +-----------+-----------+
              |                       |
     +--------+--------+    +---------+---------+
     |   FastAPI API   |    |   ARQ Worker     |
     |   :8000          |    |   WorkerSettings |
     |                  |    |   (all tasks)    |
     |  /api/v1/users  |    |   max_jobs=50    |
     |  /api/v1/jobs    |    |                  |
     |  /api/v1/reports |    |   email_tasks    |
     |  /api/v1/payments|    |   image_tasks    |
     |  /api/v1/webhooks|    |   report_tasks   |
     +------------------+    |   payment_tasks   |
                             |   etl_tasks       |
                             |   webhook_tasks   |
                             |   notification    |
                             |   cleanup (cron)  |
                             +------------------+
```

### Microservice Mode

```
                    +-----------+
                    |  Redis    |
                    |  :6379    |
                    +-----+-----+
                          |
              +-----------+-----------+-----------+
              |           |           |           |
     +--------+--+  +-----+---+  +----+----+  +--+------+
     | FastAPI   |  | Worker  |  | Worker  |  | Worker  |
     | :8000     |  | Email   |  | Payment |  | Report  |
     |           |  | queue:  |  | queue:  |  | queue:  |
     | (enqueues |  | "email" |  |"payment"|  |"report" |
     |  to       |  +---------+  +---------+  +---------+
     |  specific |     +------------------+------------------+
     |  queues)  |     |   General Worker (WorkerSettings)  |
     +----------+      |   default queue + cron cleanup    |
                         +-----------------------------------+
```

---

## 4. Directory Structure

```
task_queue_project/
├── docker-compose.yml          # Monolithic: API + worker + Redis
├── docker-compose.micro.yml   # Microservice: per-domain workers
├── Dockerfile                 # API server container
├── Dockerfile.worker           # ARQ worker container
├── requirements.txt
├── pyproject.toml              # pytest config
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app with lifespan (Redis pool init)
│   ├── config.py               # Pydantic Settings (Redis, DB config)
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── arq_utils.py             # Redis pool singleton (get_redis_pool, close_redis_pool)
│   ├── deps.py                  # FastAPI dependency injection
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── user.py              # User model
│   │   ├── job_log.py           # JobLog + JobStatus enum
│   │   ├── report.py            # Report + ReportType/ReportStatus enums
│   │   └── payment.py           # Payment + PaymentStatus enum
│   │
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── user.py
│   │   ├── job.py               # JobCreate, JobRead, JobStatusResponse
│   │   ├── report.py
│   │   ├── payment.py
│   │   └── webhook.py
│   │
│   ├── api/                     # FastAPI routers
│   │   ├── router.py            # Aggregates all routers
│   │   ├── users.py             # POST/GET users (enqueues welcome email)
│   │   ├── jobs.py              # Enqueue jobs, check status, poll results
│   │   ├── reports.py           # Generate reports (async/sync toggle)
│   │   ├── payments.py          # Process payments with idempotency
│   │   └── webhooks.py          # Dispatch and retry webhooks
│   │
│   ├── services/                # Business logic (shared between sync/async)
│   │   ├── email_service.py
│   │   ├── image_service.py
│   │   ├── report_service.py
│   │   ├── payment_service.py
│   │   ├── etl_service.py
│   │   ├── webhook_service.py
│   │   └── notification_service.py
│   │
│   └── tasks/                   # ARQ task definitions
│       ├── worker.py             # WorkerSettings (monolithic + microservice)
│       ├── email_tasks.py        # send_welcome_email, send_report_email, send_batch_email
│       ├── image_tasks.py        # generate_thumbnail (Retry), resize_image (func() config)
│       ├── report_tasks.py       # generate_pdf_report, generate_csv_export (task chaining)
│       ├── payment_tasks.py      # process_payment (Retry + idempotency), process_refund
│       ├── etl_tasks.py          # run_data_pipeline, sync_external_data (Retry backoff)
│       ├── webhook_tasks.py      # dispatch_webhook (Retry), retry_webhook (_job_id)
│       ├── notification_tasks.py # send_push_notification, batch_notify (fan-out)
│       └── cleanup_tasks.py      # @cron jobs: cleanup_expired_sessions, cleanup_old_jobs
│
└── tests/
    ├── conftest.py               # Fixtures: TestClient, mock Redis, test DB
    ├── test_email_tasks.py
    ├── test_image_tasks.py
    ├── test_report_tasks.py
    ├── test_payment_tasks.py
    ├── test_etl_tasks.py
    ├── test_webhook_tasks.py
    ├── test_notification_tasks.py
    ├── test_cleanup_tasks.py
    ├── test_worker_settings.py
    └── test_services.py
```

---

## 5. Step 1: Foundation - Config and Database

### `app/config.py` - Centralized Configuration

The project uses **Pydantic Settings** for environment-based configuration. This means you can set Redis host, port, password, and database URL via environment variables or a `.env` file.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0
    DATABASE_URL: str = "sqlite+aiosqlite:///./task_queue.db"

    @property
    def redis_settings(self):
        from arq.connections import RedisSettings
        return RedisSettings(
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            password=self.REDIS_PASSWORD,
            database=self.REDIS_DB,
        )

    model_config = {"env_file": ".env", "env_prefix": ""}
```

**Key takeaway**: The `redis_settings` property converts our app config into an `arq.connections.RedisSettings` object that both the API and worker can use. In Docker, we set `REDIS_HOST=redis` and the connection "just works".

### `app/database.py` - Async SQLAlchemy

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Why async?** ARQ tasks are async functions. Using `aiosqlite` means the database operations inside tasks won't block the event loop.

### `app/arq_utils.py` - Redis Pool Singleton

```python
from arq import create_pool
from arq.connections import ArqRedis

_redis_pool: ArqRedis | None = None

async def get_redis_pool() -> ArqRedis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(settings.redis_settings)
    return _redis_pool

async def close_redis_pool():
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close(close_connection_pool=True)
        _redis_pool = None
```

**Key pattern**: We maintain a **singleton Redis pool** that is created once during FastAPI startup and closed on shutdown. Both the API routes and tasks use this same pool. The `ArqRedis` object returned by `create_pool` provides the `enqueue_job()` method.

---

## 6. Step 2: Data Models and Schemas

### SQLAlchemy Models

The project defines four models that represent the persistent state:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `User` | API users | `email`, `username`, `is_active` |
| `JobLog` | Track every enqueued ARQ job | `arq_job_id`, `task_name`, `status`, `input_data`, `result_data` |
| `Report` | Generated reports | `title`, `report_type` (pdf/csv), `status`, `file_path` |
| `Payment` | Payment transactions | `amount`, `status`, `idempotency_key`, `external_id` |

**The `JobLog` model** is the bridge between the database and ARQ. When the API enqueues a job, it:
1. Calls `redis.enqueue_job("task_name", *args)` which returns a `Job` object with a `job_id`
2. Stores that `job_id` in `JobLog.arq_job_id` along with the task name and input data
3. Later, the `/jobs/{job_id}/status` endpoint can use `ArqRedis` to check the job's progress

### Pydantic Schemas

Each model has a `Create` schema (for input) and a `Read` schema (for output). For example, `JobCreate` accepts a `task_name` and optional `idempotency_key`, while `JobRead` includes the full database record.

---

## 7. Step 3: ARQ Task Definitions

This is the core of the project. Each task module demonstrates specific ARQ features.

### 7.1 Email Tasks - Basic Enqueue and Fan-Out

```python
# app/tasks/email_tasks.py

async def send_welcome_email(ctx: dict, user_id: int) -> dict:
    """ARQ Feature: Basic enqueue + _job_id for deduplication.

    The API route calls:
      await redis.enqueue_job("send_welcome_email", user.id,
                               _job_id=f"welcome_email_{user.id}")

    The _job_id prevents duplicate welcome emails.
    """
    email_service = ctx.get("email_service", EmailService())
    result = await email_service.send_welcome(user_id)
    return {"user_id": user_id, "email_sent": True, **result}

async def send_batch_email(ctx: dict, user_ids: list[int], subject: str, body: str) -> dict:
    """ARQ Feature: Fan-out pattern.

    This task enqueues individual send_welcome_email tasks
    for each user in the batch.
    """
    redis: ArqRedis = ctx["redis"]
    job_ids = []
    for uid in user_ids:
        job = await redis.enqueue_job("send_welcome_email", uid)
        if job:
            job_ids.append(job.job_id)
    return {"total": len(user_ids), "enqueued": len(job_ids), "job_ids": job_ids}
```

**What you learn**:
- Every task function receives a `ctx` dict as its first argument
- `ctx["redis"]` gives you the `ArqRedis` pool for enqueuing follow-up tasks
- `ctx.get("email_service", EmailService())` uses a service from the worker context or creates a default

### 7.2 Image Tasks - Retry with Exponential Backoff

```python
# app/tasks/image_tasks.py

async def generate_thumbnail(ctx: dict, image_url: str, size: str = "200x200") -> dict:
    """ARQ Feature: Retry with exponential backoff.

    If the image service is unavailable, raise Retry(defer=N).
    The defer value increases with each retry: 5s, 10s, 15s...
    """
    try:
        result = await image_service.create_thumbnail(image_url, size)
        return {"thumbnail_path": result["thumbnail_path"]}
    except Exception:
        raise Retry(defer=ctx.get("job_try", 1) * 5)
```

**How Retry works**:
1. The worker catches `Retry` exceptions
2. It re-enqueues the job with a new score (current time + `defer` seconds)
3. `ctx["job_try"]` increments on each attempt
4. After `max_tries` (default 5), the job fails permanently
5. `defer_score` is stored in milliseconds: `defer=5` becomes `defer_score=5000`

### 7.3 Report Tasks - Task Chaining

```python
# app/tasks/report_tasks.py

async def generate_pdf_report(ctx: dict, report_id: int) -> dict:
    """ARQ Feature: Task chaining with _defer_by.

    After generating the PDF, this task enqueues a follow-up
    email task that fires 60 seconds later.
    """
    result = await report_service.generate_pdf(report_id)

    redis: ArqRedis = ctx["redis"]
    await redis.enqueue_job("send_report_email", user_id, report_id, _defer_by=60)

    return {"report_id": report_id, "status": "completed"}
```

**What you learn**: Tasks can enqueue other tasks. The `_defer_by=60` means the email waits 60 seconds before sending, giving the user time to download the report first.

### 7.4 Payment Tasks - Idempotency with _job_id

```python
# app/tasks/payment_tasks.py

async def process_payment(ctx: dict, payment_id: int) -> dict:
    """ARQ Feature: Idempotent processing with _job_id.

    The API route enqueues this with:
      _job_id=f"payment_{idempotency_key}"

    If the same payment is enqueued twice with the same _job_id,
    the second call returns None and the job is not duplicated.
    """
    try:
        result = await payment_service.process(payment_id)
        return {"payment_id": payment_id, "external_id": result.get("external_id")}
    except Exception:
        raise Retry(defer=ctx.get("job_try", 1) * 10)
```

**In the API route** (`app/api/payments.py`):

```python
job_id = payment_in.idempotency_key or f"payment_{payment.id}"
await redis.enqueue_job("process_payment", payment.id, _job_id=job_id, _queue_name="payment")
```

### 7.5 Webhook Tasks - Retry with Backoff and Custom _job_id

```python
async def dispatch_webhook(ctx: dict, url: str, payload: dict, event_type: str) -> dict:
    """ARQ Feature: Retry for unreliable external services.

    Webhooks are inherently unreliable. This task retries
    with exponential backoff: 5s, 10s, 15s, 20s, 25s.
    """
    try:
        result = await webhook_service.dispatch(url, payload, event_type)
        return {"status_code": result.get("status_code")}
    except Exception:
        raise Retry(defer=ctx.get("job_try", 1) * 5)
```

### 7.6 Notification Tasks - Fan-Out Pattern

```python
async def batch_notify(ctx: dict, user_ids: list[int], message: str) -> dict:
    """ARQ Feature: Fan-out - one task triggers many sub-tasks.

    Instead of sending 1000 notifications sequentially,
    this enqueues 1000 individual tasks that the worker
    processes in parallel (up to max_jobs concurrent).
    """
    redis: ArqRedis = ctx["redis"]
    for uid in user_ids:
        await redis.enqueue_job("send_push_notification", uid, message)
```

### 7.7 Cleanup Tasks - Cron Jobs

```python
from arq import cron

async def cleanup_expired_sessions(ctx: dict) -> dict:
    """Cron job that runs every hour."""
    # Cleanup logic...
    return {"expired_sessions_removed": count}

async def cleanup_old_job_results(ctx: dict) -> dict:
    """Cron job that runs daily at 2 AM."""
    # Cleanup logic...
    return {"old_jobs_removed": count}

# These are defined as cron jobs:
cron_cleanup_sessions = cron(
    cleanup_expired_sessions,
    hour="*", minute=0,       # Every hour at minute 0
    run_at_startup=True,       # Also runs when worker starts
    unique=True,               # Only one instance at a time
)

cron_cleanup_old_jobs = cron(
    cleanup_old_job_results,
    hour=2, minute=0,         # Daily at 2:00 AM
    unique=True,               # Prevents overlapping runs
)
```

**What you learn**:
- `@cron` decorator converts an async function into a `CronJob`
- `run_at_startup=True` runs the job immediately when the worker starts
- `unique=True` ensures only one instance runs even with multiple workers
- Cron schedule uses standard syntax: `hour="*"`, `minute=0`, etc.

---

## 8. Step 4: The Worker - ARQ's Engine

The worker is a separate process that connects to Redis, polls for jobs, and executes task functions. Its configuration lives in the `WorkerSettings` class.

### `app/tasks/worker.py` - Monolithic Worker

```python
from arq import func
from arq.connections import RedisSettings
from httpx import AsyncClient

async def on_worker_startup(ctx: dict):
    """ARQ Feature: on_startup hook.

    Creates shared resources available to all tasks via ctx.
    """
    ctx["http_client"] = AsyncClient(timeout=30.0)
    ctx["worker_started_at"] = datetime.now(timezone.utc).isoformat()

async def on_worker_shutdown(ctx: dict):
    """ARQ Feature: on_shutdown hook. Cleans up resources."""
    await ctx["http_client"].aclose()

class WorkerSettings:
    """Monolithic worker - processes ALL task types."""

    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown

    functions = [
        send_welcome_email,
        send_report_email,
        send_batch_email,
        generate_thumbnail,
        func(resize_image, keep_result=86400, max_tries=3),  # Custom config
        generate_pdf_report,
        generate_csv_export,
        func(process_payment, max_tries=3),                  # Only 3 attempts
        process_refund,
        run_data_pipeline,
        sync_external_data,
        dispatch_webhook,
        retry_webhook,
        send_push_notification,
        batch_notify,
        func(generate_pdf_report, name="generate_pdf_report_long",
             timeout=600, keep_result=3600),                  # 10-min timeout
    ]

    cron_jobs = [cron_cleanup_sessions, cron_cleanup_old_jobs]

    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 50          # Maximum concurrent jobs
    retry_jobs = True      # Auto-retry on Retry exception
    max_tries = 5          # Default max retries per job
    job_timeout = 300      # Default 5-minute timeout
    keep_result = 3600     # Keep results for 1 hour
```

**Key ARQ concepts in WorkerSettings**:

| Setting | What it does |
|---------|-------------|
| `functions` | List of task functions the worker can execute |
| `func(task, ...)` | Wrapper to set per-task `max_tries`, `timeout`, `keep_result` |
| `cron_jobs` | Scheduled recurring tasks |
| `on_startup` | Async function called once when worker starts (for shared resources) |
| `on_shutdown` | Async function called once when worker stops (for cleanup) |
| `max_jobs` | How many jobs can run concurrently |
| `retry_jobs` | Whether to re-queue jobs that raise `Retry` |
| `max_tries` | Default maximum retry attempts |
| `job_timeout` | Default timeout in seconds |
| `keep_result` | How long (seconds) to keep job results in Redis |
| `redis_settings` | Redis connection configuration |
| `queue_name` | Which Redis queue to poll (default: `"arq:queue"`) |

### Microservice Workers

The same file defines three additional worker classes for microservice deployment:

```python
class WorkerSettingsEmail:
    """Processes only email tasks from the "email" queue."""
    functions = [send_welcome_email, send_report_email, send_batch_email]
    queue_name = "email"       # <--- Queue isolation
    max_jobs = 20

class WorkerSettingsPayment:
    """Processes only payment tasks from the "payment" queue."""
    functions = [func(process_payment, max_tries=3), process_refund]
    queue_name = "payment"
    max_jobs = 10

class WorkerSettingsReport:
    """Processes only report tasks from the "report" queue."""
    functions = [generate_pdf_report, generate_csv_export, generate_thumbnail, ...]
    queue_name = "report"
    max_jobs = 10
```

The API route specifies which queue to use when enqueuing:

```python
# In app/api/reports.py:
await redis.enqueue_job("generate_pdf_report", report.id, _queue_name="report")

# In app/api/payments.py:
await redis.enqueue_job("process_payment", payment.id, _queue_name="payment")
```

---

## 9. Step 5: Service Layer

The service modules contain **actual business logic** that can be called both:
- **Synchronously** from API routes (when `async_mode=False`)
- **Asynchronously** from ARQ tasks (when running in the worker)

For example, `app/services/payment_service.py`:

```python
class PaymentService:
    async def process(self, payment_id: int) -> dict:
        # Real payment processing logic would go here
        # (call Stripe API, update database, etc.)
        return {"payment_id": payment_id, "external_id": f"pay_{uuid.uuid4().hex[:12]}"}

    async def refund(self, payment_id: int, reason: str | None = None) -> dict:
        # Real refund logic
        return {"payment_id": payment_id, "refund_amount": 0.0, "status": "refunded"}
```

**Why this pattern?** It enables the **dual-mode API** where endpoints can either:
1. Enqueue a background task and return immediately (`async_mode=True`)
2. Execute the service directly and return the result (`async_mode=False`)

---

## 10. Step 6: API Routes - Enqueue and Poll

### Enqueuing a Job

The API routes create a Redis pool, call `enqueue_job()`, and return the job ID:

```python
# app/api/payments.py
@router.post("/process", response_model=PaymentRead)
async def process_payment_endpoint(payment_in: PaymentCreate, db: AsyncSession = Depends(get_db)):
    # ... create payment record in database ...

    if payment_in.async_mode:
        # ARQ: enqueue background task
        redis = await get_redis_pool()
        job_id = payment_in.idempotency_key or f"payment_{payment.id}"
        await redis.enqueue_job(
            "process_payment",
            payment.id,
            _job_id=job_id,           # Idempotency key
            _queue_name="payment",      # Microservice queue
        )
    else:
        # Sync: call service directly
        result = await PaymentService().process(payment.id)
        payment.status = PaymentStatus.COMPLETED
        # ...

    return payment
```

### Checking Job Status

The `/jobs/{job_id}/status` endpoint shows how to poll ARQ for job results:

```python
# app/api/jobs.py
@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    redis = await get_redis_pool()
    arq_job = ArqJob(job_id=job_id, redis=redis)

    status = await arq_job.status()         # "queued", "in_progress", "complete"
    result = None
    if status.value == "complete":
        result = str(await arq_job.result(timeout=1))

    return JobStatusResponse(arq_job_id=job_id, status=status.value, result=result)
```

**ARQ Job lifecycle**: `queued` -> `in_progress` -> `complete` (or `not_found` if expired)

---

## 11. Step 7: FastAPI Application with Lifespan

The FastAPI app uses an **async context manager** for startup/shutdown of shared resources:

```python
# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()          # Create database tables
    await get_redis_pool()   # Initialize ARQ Redis connection pool
    yield
    await close_redis_pool() # Clean up Redis connections

app = FastAPI(title="Task Queue API", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
```

**How it all connects**:
1. Request hits FastAPI (`:8000/api/v1/payments/process`)
2. Route creates a database record, enqueues a job via Redis
3. ARQ worker (running separately) picks up the job from Redis
4. Worker executes the task function, which calls the service layer
5. Task result is stored in Redis (for `keep_result` seconds)
6. API can poll `/api/v1/jobs/{job_id}/status` to check progress

---

## 12. Step 8: Docker Deployment

### Monolithic Mode (single worker)

```bash
docker compose up
```

This starts:
- **Redis** on port 6379 (with health check)
- **API server** on port 8000
- **ARQ worker** (`arq app.tasks.worker.WorkerSettings`)

### Microservice Mode (domain-isolated workers)

```bash
docker compose -f docker-compose.micro.yml up
```

This starts:
- **Redis** on port 6379
- **API server** on port 8000
- **Email worker** (`arq app.tasks.worker.WorkerSettingsEmail`, queue: `email`)
- **Payment worker** (`arq app.tasks.worker.WorkerSettingsPayment`, queue: `payment`)
- **Report worker** (`arq app.tasks.worker.WorkerSettingsReport`, queue: `report`)
- **General worker** (`arq app.tasks.worker.WorkerSettings`, default queue + cron)

The API routes use `_queue_name` to route jobs to specific queues.

---

## 13. Step 9: Testing

The project has 50 tests covering tasks, services, worker configuration, and ARQ features.

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures (test DB, mock Redis, mock job)
├── test_email_tasks.py      # 4 tests: basic enqueue, _job_id dedup, fan-out
├── test_image_tasks.py      # 3 tests: success, Retry with backoff, func() config
├── test_report_tasks.py    # 4 tests: PDF, CSV, task chaining verification
├── test_payment_tasks.py   # 4 tests: success, Retry, refund, idempotency
├── test_etl_tasks.py        # 3 tests: pipeline, sync, Retry backoff verification
├── test_webhook_tasks.py   # 3 tests: dispatch, retry, _job_id uniqueness
├── test_notification_tasks.py # 4 tests: push, fan-out, partial fan-out
├── test_cleanup_tasks.py   # 2 tests: cron job execution
├── test_worker_settings.py # 7 tests: functions, cron, config, queues, lifecycle
└── test_services.py         # 16 tests: all service methods
```

### Key Testing Patterns

**Testing task functions directly** (no Redis needed):

```python
@pytest.mark.asyncio
async def test_send_welcome_email():
    ctx = {"email_service": EmailService()}
    result = await send_welcome_email(ctx, user_id=1)
    assert result["user_id"] == 1
    assert result["email_sent"] is True
```

**Testing Retry behavior**:

```python
@pytest.mark.asyncio
async def test_generate_thumbnail_retry():
    mock_service = AsyncMock()
    mock_service.create_thumbnail = AsyncMock(side_effect=Exception("timeout"))

    ctx = {"image_service": mock_service, "job_try": 2}
    with pytest.raises(Retry) as exc_info:
        await generate_thumbnail(ctx, image_url="...", size="200x200")
    # defer_score is in milliseconds: job_try * 5 * 1000
    assert exc_info.value.defer_score == 10000  # 2 * 5 * 1000
```

**Testing fan-out with mock Redis**:

```python
@pytest.mark.asyncio
async def test_batch_notify_fan_out():
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "push-job-1"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"redis": mock_redis}
    result = await batch_notify(ctx, user_ids=[1, 2, 3], message="Hello!")
    assert result["total_users"] == 3
    assert mock_redis.enqueue_job.call_count == 3
```

**Testing WorkerSettings configuration**:

```python
def test_worker_settings_functions():
    function_names = [f.name if hasattr(f, "name") else f.__name__
                      for f in WorkerSettings.functions]
    assert "send_welcome_email" in function_names
    assert "process_payment" in function_names

def test_worker_settings_config():
    assert WorkerSettings.max_jobs == 50
    assert WorkerSettings.retry_jobs is True
    assert WorkerSettings.max_tries == 5
```

### Running Tests

```bash
cd task_queue_project
source taskqueueenv/bin/activate    # activate the project virtual environment
uv pip install -r requirements.txt  # install dependencies with uv
python -m pytest tests/ -v         # run all 50 tests
```

No Redis required for tests - all task tests use mock contexts and mock Redis pools.

---

## 14. ARQ Feature Reference

A complete reference of every ARQ feature demonstrated in this project:

### Enqueueing Jobs

```python
redis = await get_redis_pool()

# Basic enqueue
await redis.enqueue_job("send_push_notification", user_id=1, message="Hello")

# With job_id for uniqueness (prevents duplicates)
await redis.enqueue_job("process_payment", payment_id, _job_id=f"payment_{key}")

# With defer_by (delay execution by N seconds)
await redis.enqueue_job("send_report_email", user_id, report_id, _defer_by=60)

# With queue_name (route to specific worker)
await redis.enqueue_job("generate_pdf_report", report_id, _queue_name="report")
```

### Task Definition Patterns

```python
# Basic task
async def my_task(ctx: dict, arg1: int) -> dict:
    return {"result": "done"}

# Retry with exponential backoff
async def flaky_task(ctx: dict, url: str) -> dict:
    try:
        return await fetch(url)
    except Exception:
        raise Retry(defer=ctx.get("job_try", 1) * 5)

# Task chaining (enqueue follow-up)
async def parent_task(ctx: dict, data_id: int) -> dict:
    result = await process(data_id)
    redis: ArqRedis = ctx["redis"]
    await redis.enqueue_job("child_task", result["id"])
    return result

# Fan-out (one task -> many tasks)
async def fan_out_task(ctx: dict, user_ids: list[int]) -> dict:
    redis: ArqRedis = ctx["redis"]
    for uid in user_ids:
        await redis.enqueue_job("notify_user", uid)
```

### Worker Configuration

```python
from arq import func, cron
from arq.connections import RedisSettings

class WorkerSettings:
    on_startup = startup_func       # Initialize shared resources
    on_shutdown = shutdown_func      # Clean up shared resources

    functions = [
        basic_task,                                       # Default config
        func(heavy_task, timeout=600, keep_result=3600),  # 10-min timeout
        func(payment_task, max_tries=3),                  # Only 3 retry attempts
    ]

    cron_jobs = [
        cron(cleanup_func, hour=2, minute=0, unique=True),
        cron(heartbeat, minute="*/5", run_at_startup=True),
    ]

    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 50
    retry_jobs = True
    max_tries = 5
    job_timeout = 300
    keep_result = 3600
    queue_name = "arq:queue"       # Default queue name
    health_check_key = "arq:health"
```

### Job Result Polling

```python
from arq.jobs import Job as ArqJob

# Enqueue
job = await redis.enqueue_job("my_task", 42)
job_id = job.job_id

# Check status
job = ArqJob(job_id=job_id, redis=redis)
status = await job.status()  # JobStatus.queued / in_progress / complete

# Get result
result = await job.result(timeout=10)  # Wait up to 10 seconds

# Get info
info = await job.info()  # JobDef(function='my_task', args=(42,), ...)
```

### func() Wrapper Options

```python
from arq import func

func(
    my_task,
    name="custom_name",        # Override function name
    max_tries=3,                # Override default max_tries
    timeout=600,                # Override default job_timeout (seconds)
    keep_result=86400,          # Keep result for 24 hours (seconds)
    keep_result_forever=False,  # Never expire the result
)
```

### Cron Job Options

```python
from arq import cron

cron(
    my_task,
    month="*",           # 1-12 or "*"
    day="*",             # 1-31 or "*"
    weekday="*",         # 0-6 (Mon=0) or "mon","tue",...
    hour=2,               # 0-23
    minute=0,             # 0-59
    second=0,             # 0-59
    microsecond=123456,   # 0-1e6 (default avoids top-of-second)
    run_at_startup=False,  # Run immediately when worker starts
    unique=True,           # Prevent overlapping runs
    job_id="my_cron_id",  # Custom job ID
    timeout=300,           # Job timeout in seconds
    keep_result=3600,      # How long to keep results
    max_tries=3,            # Max retries for this cron job
)
```

---

## 15. Running the Project

### Local Development (without Docker)

```bash
# 1. Activate the virtual environment (located in the project root)
source taskqueueenv/bin/activate

# 2. Install dependencies (uv is used as the package manager)
uv pip install -r requirements.txt

# 3. Start Redis (local or Docker)
docker run -d -p 6379:6379 redis:7-alpine

# 4. Start the API server
cd task_queue_project
uvicorn app.main:app --reload --port 8000

# 5. In another terminal, start the ARQ worker
arq app.tasks.worker.WorkerSettings

# 6. Run tests (no Redis needed)
python -m pytest tests/ -v
```

### Docker Compose (Monolithic)

```bash
cd task_queue_project
docker compose up
```

Starts Redis + API + Worker. Visit `http://localhost:8000/docs` for the Swagger UI.

### Docker Compose (Microservice)

```bash
cd task_queue_project
docker compose -f docker-compose.micro.yml up
```

Starts Redis + API + 4 domain-specific workers (email, payment, report, general).

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/users/` | Create user + enqueue welcome email |
| GET | `/api/v1/users/` | List users |
| GET | `/api/v1/users/{id}` | Get user |
| POST | `/api/v1/jobs/enqueue` | Enqueue any ARQ task |
| GET | `/api/v1/jobs/` | List recent job logs |
| GET | `/api/v1/jobs/{id}` | Get job log |
| GET | `/api/v1/jobs/{id}/status` | Poll ARQ job status |
| POST | `/api/v1/reports/generate` | Generate report (async/sync toggle) |
| GET | `/api/v1/reports/` | List reports |
| POST | `/api/v1/payments/process` | Process payment with idempotency |
| POST | `/api/v1/payments/refund` | Refund a payment |
| POST | `/api/v1/webhooks/dispatch` | Dispatch webhook (fire-and-forget) |
| POST | `/api/v1/webhooks/retry/{id}` | Retry a failed webhook |
| GET | `/health` | Health check |

### Quick Test with curl

```bash
# Create a user (triggers welcome email task)
curl -X POST http://localhost:8000/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "username": "testuser", "full_name": "Test User"}'

# Enqueue a job
curl -X POST http://localhost:8000/api/v1/jobs/enqueue \
  -H "Content-Type: application/json" \
  -d '{"task_name": "send_push_notification", "input_data": "[1, \"Hello!\"]"}'

# Process a payment (async)
curl -X POST http://localhost:8000/api/v1/payments/process \
  -H "Content-Type: application/json" \
  -d '{"amount": 29.99, "user_id": 1, "idempotency_key": "order_123"}'

# Generate a PDF report (async)
curl -X POST http://localhost:8000/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"title": "Monthly", "report_type": "pdf", "user_id": 1, "async_mode": true}'
```

---

## Summary

This project demonstrates a complete, production-ready pattern for integrating **ARQ** with **FastAPI**:

1. **Enqueue** jobs from API routes via `redis.enqueue_job()`
2. **Process** jobs in a separate worker process via `WorkerSettings`
3. **Track** job status via the `Job` class and persistent `JobLog` model
4. **Retry** failed jobs with exponential backoff via `Retry(defer=N)`
5. **Deduplicate** jobs with `_job_id` for idempotent processing
6. **Schedule** future jobs with `_defer_by` and `_defer_until`
7. **Chain** tasks by enqueuing follow-up jobs from within a task
8. **Fan out** by enqueuing many sub-tasks from one parent task
9. **Configure** per-task behavior with `func()` (timeout, max_tries, keep_result)
10. **Schedule** recurring cleanup with `@cron`
11. **Isolate** domains with `queue_name` for microservice deployment
12. **Share** resources across tasks with `on_startup`/`on_shutdown`

---

## 16. Appendix A: End-to-End Stage Walkthrough

This appendix walks the project from its very first line of code to a
fully running production deployment. Each stage answers three questions:

- **What is the problem?**
- **Which file(s) solve it?**
- **What does the resulting flow look like?**

Read it linearly the first time — every stage builds on the previous.

---

### Stage 0 — The Problem We Are Solving

Imagine a FastAPI endpoint `POST /users/` that has to do five things
when a new account is created:

1. Validate the request body
2. Insert a row into the `users` table
3. Send a welcome email
4. Pre-generate the user's first dashboard report
5. Push a notification to admins

If you do all five **inside the request handler**, the client waits for
every step. The email server alone may take 2-5 seconds. The user's
browser hangs, requests time out, and your p99 latency dies.

The classic fix: do the fast work (1–2) inline, then **enqueue** the
slow work (3–5) to a background worker. ARQ is the queue that lets us
do that with async Python and Redis.

---

### Stage 1 — Plumbing the Config (`app/config.py`)

Before we can talk to Redis or the database, we need a single source of
truth for connection strings. Pydantic-Settings reads env vars + a
`.env` file and validates types at import time, so a typo in
`REDIS_PORT=abc` fails on boot rather than at request time.

```
.env file ─┐
env vars ─ ┼─► Settings(BaseSettings) ─► settings (module-level singleton)
defaults ──┘
```

The `redis_settings` property is the bridge that converts our 4 fields
into the `RedisSettings` shape ARQ expects.

---

### Stage 2 — Connecting to the Database (`app/database.py`)

Async SQLAlchemy gives us a non-blocking engine + a session factory.
The flow at boot is:

```
import app.database
      │
      ▼
create_async_engine(DATABASE_URL)   # opens the connection pool
      │
      ▼
async_sessionmaker(engine, ...)     # factory for AsyncSession instances
      │
      ▼
Base = DeclarativeBase              # parent class for every ORM model
```

`init_db()` is a one-shot DDL helper that calls `Base.metadata.create_all`
inside an async-friendly wrapper. Models register themselves on
`Base.metadata` simply by **being imported** — which is why
`app/models/__init__.py` imports each module explicitly.

---

### Stage 3 — Building the Redis Pool (`app/arq_utils.py`)

Creating a Redis pool per request would burn CPU on the TCP handshake.
Instead we maintain a single module-level pool:

```
First request: get_redis_pool() ──► _redis_pool is None ──► create_pool(...)
                                          │
Next request:  get_redis_pool() ──► already exists ──► return same object
                                          │
Shutdown:      close_redis_pool() ──► close & set None
```

This pool is the object you call `.enqueue_job(...)` on.

---

### Stage 4 — Modelling the Domain (`app/models/*.py`)

Four tables, each with a clear purpose:

| Table     | Role                                          |
|-----------|-----------------------------------------------|
| `users`    | Accounts. Parent of payments + reports.       |
| `payments` | Money transactions, plus an idempotency key. |
| `reports`  | Async report artefacts (PDF/CSV).             |
| `job_logs` | **Audit trail** for every ARQ enqueue.        |

The audit pattern is important. ARQ already stores results in Redis,
but Redis is volatile and short-lived (`keep_result` defaults to 1h).
`job_logs` is the long-term, queryable record we hand to support staff
and ops dashboards.

Foreign keys plus `relationship(...)` give us SQLAlchemy joins for
free — e.g. `user.payments` returns a list of `Payment` objects.

---

### Stage 5 — Designing the Wire Format (`app/schemas/*.py`)

Pydantic schemas describe what JSON the API accepts and emits. They
are deliberately **separate** from the ORM models because the two have
different concerns:

- ORM models = how the data is **stored** (FKs, indexes, defaults)
- Pydantic schemas = how the data is **transferred** (validation, JSON)

Each domain has a `XxxCreate` (input) and `XxxRead` (output) pair.
`from_attributes=True` is the magic that lets FastAPI return an ORM
object directly — Pydantic will read its attributes.

---

### Stage 6 — Writing the Business Logic (`app/services/*.py`)

Services are plain async classes with NO knowledge of:

- FastAPI (no `Request`, no dependency injection)
- ARQ (no `ctx` dict, no `Retry`)
- Redis (no pool)

That decoupling is exactly what enables the dual sync/async mode in
the API — the same `PaymentService.process(payment_id)` runs from a
route handler (sync mode) and from an ARQ task (async mode).

In a real codebase these would call Stripe, SendGrid, S3, etc. Here
they return deterministic dicts so tests stay hermetic.

---

### Stage 7 — Writing the Tasks (`app/tasks/*.py`)

A task is an `async def` whose first parameter is `ctx: dict`. ARQ
will populate `ctx` with:

```
ctx = {
  "redis":   ArqRedis,        # the pool (for enqueuing more jobs)
  "job_try": 1,                # how many attempts so far
  "job_id":  "abc123",        # this job's id
  "score":   1716_..._.0,      # the Redis-side score
  "enqueue_time": datetime,
  # plus anything you stored in on_startup
}
```

Patterns demonstrated, in roughly increasing complexity:

1. **Fire-and-forget** — `send_push_notification` just does the work.
2. **Service injection** — every task accepts an optional service from
   ctx (`ctx.get("email_service", EmailService())`).
3. **Retry with backoff** — `dispatch_webhook` wraps the work in
   `try/except` and raises `Retry(defer=ctx['job_try'] * 5)`.
4. **Task chaining** — `generate_pdf_report` enqueues
   `send_report_email` with `_defer_by=60`.
5. **Fan-out** — `batch_notify` enqueues one
   `send_push_notification` per user.
6. **Cron** — `cleanup_expired_sessions` is wrapped with `cron(...)`
   to run hourly + at startup.

---

### Stage 8 — Wiring the Worker (`app/tasks/worker.py`)

`WorkerSettings` is the recipe the `arq` CLI follows:

```
arq app.tasks.worker.WorkerSettings
   │
   ▼
ARQ reads:
   ├── functions      → the task registry
   ├── cron_jobs      → the scheduler
   ├── redis_settings → where to poll
   ├── on_startup     → initialise ctx
   ├── on_shutdown    → tear down ctx
   └── max_jobs, max_tries, job_timeout, keep_result
```

`func(fn, ...)` is the **per-task** override mechanism. Want one
specific task to have a 10-minute timeout? Wrap it:

```python
func(generate_pdf_report, timeout=600, keep_result=3600)
```

For microservices we duplicate this class once per domain, each with
its own `queue_name`. Routes enqueue to those queues by passing
`_queue_name="email"|"payment"|"report"`.

---

### Stage 9 — Exposing the API (`app/api/*.py`)

Each domain has its own router file. They all follow the same shape:

```
POST /domain/action
  ├── Validate via Pydantic schema
  ├── Insert/lookup DB row
  ├── if async_mode → redis.enqueue_job(...)
  ├── else          → call service inline
  └── Return the persisted row
```

Two routes deserve special attention:

- `POST /jobs/enqueue` is the **generic** enqueue endpoint — useful
  for admin tooling and the demo curl examples.
- `GET /jobs/{job_id}/status` is the **poll** endpoint. It uses
  `arq.jobs.Job(job_id, redis)` to look up the live status in Redis.

---

### Stage 10 — Booting the App (`app/main.py`)

FastAPI's `lifespan` context manager bookends the request-serving phase
with startup/shutdown logic:

```
startup:
  ├── init_db()          # CREATE TABLEs
  └── get_redis_pool()   # warm the pool

(yield → app serves traffic)

shutdown:
  └── close_redis_pool() # release sockets
```

The same `app` object is what tests import via
`ASGITransport(app=app)` and what uvicorn serves.

---

### Stage 11 — Wrapping in Containers (Dockerfile / docker-compose)

Two Dockerfiles, one for the API and one for the worker, share the
same `requirements.txt`. The Compose files orchestrate Redis + API +
one-or-more workers.

```
docker-compose.yml       → monolithic: 1 API + 1 worker + Redis
docker-compose.micro.yml → micro:      1 API + 4 workers (email/payment/report/general) + Redis
```

The general worker still owns the cron jobs in microservice mode so
cleanups always run somewhere.

---

### Stage 12 — Locking it Down with Tests (`tests/*.py`)

The test suite never touches a real Redis. Two patterns get reused:

1. **Direct task call**: build a `ctx` dict, await the task, assert
   the return shape.
2. **Mock Redis pool**: `AsyncMock()` whose `enqueue_job` returns a
   `MagicMock(job_id=...)`. Assertions on `enqueue_job.call_args_list`
   verify chaining and fan-out without a worker process.

The DB fixture (`setup_db`) recreates the schema before every test and
drops it after — guaranteeing isolation.

---

### Stage 13 — Putting it All in Motion

A full happy-path lifecycle from a single `curl`:

```
1. curl POST /api/v1/payments/process {..., idempotency_key: "abc"}
       │
       ▼
2. process_payment_endpoint() in app/api/payments.py
       ├── Validates user exists
       ├── Short-circuits if idempotency_key already used
       ├── INSERT payments row (status=PENDING)
       └── redis.enqueue_job("process_payment", payment.id,
                             _job_id="abc",
                             _queue_name="payment")
       │
       ▼
3. Redis sorted set "arq:queue:payment" now holds job "abc"
       │
       ▼
4. WorkerSettingsPayment polls the queue, claims job "abc"
       ├── Calls ctx["payment_service"].process(payment.id) (or new())
       ├── On success → returns dict with external_id
       └── On exception → raise Retry(defer=10) → job re-enqueued
       │
       ▼
5. ARQ stores the result in Redis with TTL=keep_result
       │
       ▼
6. curl GET /api/v1/jobs/abc/status
       └── arq.jobs.Job(id="abc", redis=pool).status() → "complete"
                                            .result()  → the dict
```

---

## 17. Appendix B: File-by-File Reading Guide

The annotated source files include extensive in-line comments. The
recommended reading order if you are studying the codebase:

1. `app/config.py` — environment plumbing
2. `app/database.py` — async SQLAlchemy
3. `app/arq_utils.py` — the Redis pool singleton
4. `app/models/job_log.py` — see how we audit enqueues
5. `app/services/email_service.py` — the simplest service stub
6. `app/tasks/email_tasks.py` — the simplest task module
7. `app/tasks/image_tasks.py` — adds Retry with backoff
8. `app/tasks/report_tasks.py` — adds task chaining
9. `app/tasks/notification_tasks.py` — adds fan-out
10. `app/tasks/cleanup_tasks.py` — adds cron
11. `app/tasks/worker.py` — pulls it all together
12. `app/api/users.py` — simplest enqueue from a route
13. `app/api/payments.py` — full idempotency + queue routing
14. `app/api/jobs.py` — generic enqueue + status polling
15. `app/main.py` — lifespan + router mount
16. `tests/conftest.py` — see the mocking strategy
17. `tests/test_worker_settings.py` — verifies the worker recipe

---

## 18. Appendix C: Glossary of ARQ Terms

| Term | Meaning |
|------|---------|
| **Job** | A queued unit of work — function name + args + metadata |
| **Worker** | A process that polls Redis and runs jobs |
| **ctx** | Dict passed to every task as the first argument |
| **_job_id** | Custom string id — duplicates are deduped |
| **_defer_by** | Seconds to wait before the job becomes eligible |
| **_defer_until** | Wall-clock datetime when the job becomes eligible |
| **_queue_name** | Which Redis queue (sorted set) to push the job onto |
| **Retry** | Exception that tells the worker to re-enqueue with a delay |
| **defer (in Retry)** | Seconds to wait before re-running |
| **job_try** | The 1-based attempt counter, available in ctx |
| **max_tries** | Cap on attempts before the job permanently fails |
| **keep_result** | Seconds the result is kept in Redis after completion |
| **func()** | Wrapper to set per-task `timeout`, `max_tries`, `keep_result`, `name` |
| **cron()** | Wrapper to schedule a task on a cron-like recurrence |
| **on_startup** | Async hook called once when the worker boots |
| **on_shutdown** | Async hook called once when the worker stops |
| **WorkerSettings** | Class ARQ reads to know how to run the worker |
| **health_check_key** | Redis key the worker writes to as a liveness probe |

---

## 19. Appendix D: Frequently Asked Questions

**Q: Do I have to use SQLAlchemy?**
No. ARQ has no opinion about your database. We use SQLAlchemy here to
demonstrate a realistic FastAPI + persistence + queue stack.

**Q: Can I run the worker on the same host as the API?**
Yes — that is monolithic mode. The only requirement is that both
processes can reach the same Redis.

**Q: What happens if Redis goes down mid-job?**
The worker reconnects when Redis returns. Jobs in flight when the
worker is killed are reclaimed on next startup (ARQ marks them
in_progress with a lock that expires). Jobs not yet picked up stay in
the sorted set and resume as soon as Redis is back.

**Q: How do I cancel a queued job?**
Use the ARQ CLI or call `await ArqJob(job_id, redis).abort()`. Not
exposed in this demo but trivial to add.

**Q: Can I pass complex objects as task args?**
ARQ uses msgpack by default — pass JSON-serialisable values (dicts,
lists, ints, strings, datetimes). For ORM rows, pass the primary key
and re-fetch inside the task. This avoids stale-data bugs and keeps
the payload small.

**Q: Why is `max_jobs=50` in monolithic but smaller per-microservice?**
The monolithic worker handles many domains so it needs higher
concurrency overall. Per-domain workers can tune for their specific
bottleneck — payments often throttle, reports are CPU-heavy, etc.

**Q: How do I add a new task?**
1. Write the async function under `app/tasks/<domain>_tasks.py`.
2. Add the import to `app/tasks/__init__.py` and
   `app/tasks/worker.py`.
3. Reference its name (string) from any API route via
   `await redis.enqueue_job("my_task_name", ...)`.
4. Add a unit test under `tests/test_<domain>_tasks.py`.

**Q: How do I trigger a job to run later?**
Use `_defer_by=<seconds>` or `_defer_until=<datetime>` when calling
`enqueue_job`.

**Q: How do I avoid double-execution?**
Pass `_job_id="some-stable-key"`. ARQ refuses to enqueue a second job
with the same id while the first is still alive.

**Q: Can two workers process the same queue?**
Yes — scale horizontally by running N workers with the same
`WorkerSettings`. ARQ uses Redis locks to claim jobs atomically.
