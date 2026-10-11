# FastAPI Projects Overview

A structured self-study curriculum and portfolio of 18+ advanced Python/FastAPI backend projects (numbered 0.1–16), each isolating one production concern: performance (uvloop, ASGI servers, httpx pooling), data access (Tortoise, SQLModel, asyncpg), validation, Redis patterns, background jobs (ARQ, Taskiq, multiprocessing), and observability (Prometheus, Loguru, Sentry, Logfire).

Projects 12–15 share a 1M-row `order_events` dataset to teach cursor pagination, streaming, composable pipelines, and parallel background processing, while `fastapi_notes/`, `authentication/`, and the top-level markdown files provide supporting written material and design notes.

## Project Overviews

### 0.1_uvloop_service
A FastAPI microservice for batch ingest and NDJSON streaming that benchmarks uvloop against the default asyncio event loop.
Exposes a `/metrics/loop` endpoint and includes a load-test script showing roughly 2x RPS with uvloop.

### 0.2_task_queue_project
A production-grade ARQ (async Redis queue) integration with 15+ background tasks covering retries, backoff, cron scheduling, fan-out, chaining, and idempotency.
Supports both a monolith and per-domain microservice worker modes, with 50 tests.

### 1_fastapi_asgi_uvicorn_granian
A teaching project on the ASGI interface, running the same FastAPI app under Uvicorn vs Granian (Rust).
Covers workers, Gunicorn, and CPU-bound vs IO-bound endpoint behavior.

### 2_fastapi_async_orm_sqlmodel_tortoise
A Task Manager API comparing async ORMs, with Tortoise ORM as the main app and a parallel SQLModel implementation.
Includes CRUD, lifespan integration, and Aerich/Postgres notes.

### 3_fastapi_asyncpg_database_driver
A Product Inventory API built on raw asyncpg SQL with connection pooling, a repository pattern, transactions, and SQL migrations — no ORM.

### 4_fastapi_pydantic_v2_validation
A User Registration/Profile API showcasing Pydantic v2 validators, serializers, computed fields, aliases, and discriminated unions, plus a validation benchmark.

### 5_fastapi_redis_cache2
A product management backend against real Redis demonstrating cache-aside, TTLs, invalidation, distributed locks, rate limiting, idempotency keys, counters/HLL, carts, pub/sub, and fail-open reads.

### 6_fastapi_taskiq_background_jobs
An email/report generator using Taskiq, an async-native task queue with a Redis broker.
Covers job status tracking, retries, and the success/failure lifecycle.

### 7_fastapi_slowapi_rate_limiting
A Public Quotes API teaching Slowapi rate limiting with IP and API-key strategies, tiered plans, fixed vs moving windows, 429 handling, and reverse-proxy concerns.

### 8_fastapi_prometheus_monitoring
An Orders API instrumented with prometheus-fastapi-instrumentator for latency histograms and status/throughput metrics.
Ships with Prometheus + Grafana via Docker Compose.

### 9_fastapi_loguru_structured_logging
A Payment Events API demonstrating Loguru structured JSON logging with `enqueue=True`, request correlation IDs, rotation, and bound context.

### 10_fastapi_casbin_authorization
A Document Management API enforcing RBAC/ABAC with Casbin model + CSV policy files.
Covers role inheritance, per-route enforcement, and ownership checks.

### 11_fastapi_httpx
A Weather fan-out API showing shared `httpx.AsyncClient` connection pooling via lifespan plus `asyncio.gather` concurrent upstream calls.

### 12_cursor_pagination
Keyset/cursor pagination over a 1M-row Postgres `order_events` table with SQLAlchemy async + asyncpg.
Includes resumable CSV ingestion, a composite index, and Docker scripts.

### 13_fastapi_streaming_chunking
Streaming large responses in bounded memory: server-side cursor generators for CSV/NDJSON export, report, and feed endpoints, plus a short-transaction chunked streaming variant.

### 14_fastapi_pipeline
A composable Stage-based streaming data pipeline (source → filter → chunk → transform → sink) exposed as NDJSON/CSV endpoints.
Comes with invariant tests for bounded memory, swap-ability, and fail-isolation.

### 15_backgroundjobs_async_parallel_processing
A four-part series: FastAPI BackgroundTasks audit logging; Arq+Redis CSV export; multiprocessing/PyArrow partitioned Parquet export; and idempotent, observable jobs with structured logs and Prometheus metrics.

### 16_fastapi_logging
A unified observability stack combining Loguru, Structlog, Sentry, and Pydantic Logfire with request-context propagation, dev vs prod rendering, and tests for each integration.
