# FastAPI Projects — Complete Backend Engineering Portfolio

A comprehensive collection of 18+ production-grade FastAPI projects covering async patterns, background jobs, caching, monitoring, authorization, database drivers, streaming, and more.

---

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [Why This Collection Exists](#why-this-collection-exists)
- [When to Use Each Pattern](#when-to-use-each-pattern)
- [Project Index](#project-index)
  - [0. Performance & Event Loops](#0-performance--event-loops)
  - [1. Background Jobs & Task Queues](#1-background-jobs--task-queues)
  - [2. ASGI Servers](#2-asgi-servers)
  - [3. Databases & ORMs](#3-databases--orms)
  - [4. Validation](#4-validation)
  - [5. Caching](#5-caching)
  - [6. Rate Limiting](#6-rate-limiting)
  - [7. Monitoring & Observability](#7-monitoring--observability)
  - [8. Authorization](#8-authorization)
  - [9. HTTP Clients](#9-http-clients)
  - [10. Pagination & Streaming](#10-pagination--streaming)
  - [11. Pipelines](#11-pipelines)
  - [12. Logging & Tracing](#12-logging--tracing)
  - [13. Conceptual Notes](#13-conceptual-notes)
  - [14. Utilities](#14-utilities)
- [General Setup](#general-setup)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)

---

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Layer                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   ASGI   │ │  Pydantic│ │  Casbin  │ │ Slowapi  │ │  HTTPX   │       │
│  │ Serving  │ │Validation│ │  AuthZ   │ │Rate Limit│ │  Client  │       │
│  │(Uvicorn/ │ │   v2     │ │  RBAC+   │ │ IP/Key   │ │  Async   │       │
│  │ Granian) │ │          │ │  ABAC    │ │          │ │  Pool    │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       │            │            │            │            │             │
│  ┌────┴────────────┴────────────┴────────────┴────────────┴────┐        │
│  │                    FastAPI Endpoint Layer                   │        │
│  │         StreamingResponse │ JSONResponse │ BackgroundTasks  │        │
│  └────┬────────────┬────────────┬────────────┬────────────┬────┘        │
│       │            │            │            │            │             │
│  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐       │
│  │Tortoise  │ │ asyncpg  │ │  Redis   │ │Taskiq/   │ │Multiproc │       │
│  │ ORM /    │ │ Raw SQL  │ │  Cache   │ │  ARQ     │ │  essing  │       │
│  │SQLModel  │ │ + Pool   │ │ + Locks  │ │  Queue   │ │ + PyArrow│       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Loguru / │ │Prometheus│ │  Sentry  │ │  Logfire │ │Structlog │       │
│  │ Structlog│ │+ Grafana │ │  Crash   │ │  Tracing │ │   JSON   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                     Infrastructure Layer                                │
│     PostgreSQL │ Redis │ Docker │ Docker Compose │ Nginx                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Collection Exists

This portfolio was built to answer a single question: **"What does a production-grade FastAPI application actually look like beyond the quickstart tutorial?"**

Each project isolates one backend concern and implements it the way a senior engineer would in production:

- **No mocks in caching/monitoring** — real Redis, real Prometheus, real Grafana
- **No shortcuts in auth** — Casbin RBAC/ABAC, not `if user.role == "admin"`
- **No toy datasets** — pagination and streaming projects use a real 1M-row PostgreSQL dataset
- **No "it works on my machine"** — every project with external dependencies has Docker Compose files

---

## When to Use Each Pattern

| Pattern | Project | When to Use |
|---------|---------|-------------|
| **uvloop** | `0.1_uvloop_service` | CPU-bound async workloads; ~2x throughput improvement on Linux/macOS |
| **ARQ task queue** | `0.2_task_queue_project` | Background jobs with retry, cron, chaining; Redis-native |
| **ASGI server tuning** | `1_fastapi_asgi_uvicorn_granian` | Choosing between Uvicorn, Granian, or Gunicorn+UvicornWorker |
| **Tortoise ORM** | `2_fastapi_async_orm_sqlmodel_tortoise` | Full-featured async ORM with migrations (Aerich) |
| **SQLModel** | `2_fastapi_async_orm_sqlmodel_tortoise` (alternative) | Type-safe SQLAlchemy 2.0 with Pydantic integration |
| **asyncpg raw SQL** | `3_fastapi_asyncpg_database_driver` | Maximum query performance; complex SQL; connection pooling |
| **Pydantic v2** | `4_fastapi_pydantic_v2_validation` | All new projects — Rust-powered validation, serializers, computed fields |
| **Redis caching** | `5_fastapi_redis_cache2` | Cache-aside, distributed locks, rate limiting, idempotency, leaderboards |
| **Taskiq** | `6_fastapi_taskiq_background_jobs` | Async-native task queue with Redis broker; simpler than Celery |
| **Slowapi rate limiting** | `7_fastapi_slowapi_rate_limiting` | Per-IP or per-API-key rate limiting with tiered plans |
| **Prometheus + Grafana** | `8_fastapi_prometheus_monitoring` | Production metrics, latency histograms, business KPIs |
| **Casbin RBAC/ABAC** | `10_fastapi_casbin_authorization` | Declarative authorization policies; role inheritance; resource ownership |
| **HTTPX async client** | `11_fastapi_httpx` | Fan-out HTTP calls with connection pooling; concurrent external API calls |
| **Cursor pagination** | `12_cursor_pagination` | Large datasets where OFFSET degrades; scalable pagination default |
| **Streaming response** | `13_fastapi_streaming_chunking` | Large exports, real-time feeds, bounded-memory data delivery |
| **Composable pipeline** | `14_fastapi_pipeline` | Multi-stage data processing with pluggable filter/transform/sink stages |
| **Background tasks series** | `15_backgroundjobs_async_parallel_processing` | From lightweight BackgroundTasks to multiprocessing to idempotent observable jobs |
| **Structured logging** | `16_fastapi_logging`, `9_fastapi_loguru_structured_logging` | Loguru for dev, Structlog for prod JSON, Sentry for crashes, Logfire for tracing |
| **Auth concepts** | `authentication` | Understanding API keys, sessions, JWT, OAuth2, SSO, SAML vs OIDC |

---

## Project Index

### 0. Performance & Event Loops

#### [0.1_uvloop_service](./0.1_uvloop_service)
Benchmarks uvloop vs default asyncio event loop. Demonstrates `asyncio.create_task`, `asyncio.gather`, `asyncio.as_completed`, and NDJSON streaming.

```bash
cd 0.1_uvloop_service
pip install fastapi uvicorn uvloop pydantic-settings httpx pytest
./start.sh              # uvloop on :8000
./start_default.sh      # asyncio on :8001
python load_test.py     # benchmark both
```

---

### 1. Background Jobs & Task Queues

#### [0.2_task_queue_project](./0.2_task_queue_project)
Production-grade ARQ integration with 8 task domains, retry with exponential backoff, cron scheduling, task chaining, and both monolithic and microservice deployment modes.

```bash
cd 0.2_task_queue_project
docker compose up redis -d
pip install -r requirements.txt
uvicorn app.main:app --port 8000
arq app.tasks.worker.WorkerSettings
```

#### [6_fastapi_taskiq_background_jobs](./6_fastapi_taskiq_background_jobs)
Taskiq (async-native) with Redis broker and result backend. Email report generator with job status polling.

```bash
cd 6_fastapi_taskiq_background_jobs
docker compose up -d
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
taskiq worker app.core.broker:broker app.tasks.report_tasks
```

---

### 2. ASGI Servers

#### [1_fastapi_asgi_uvicorn_granian](./1_fastapi_asgi_uvicorn_granian)
Hands-on comparison of Uvicorn, Gunicorn+UvicornWorker, and Granian (Rust-based). Covers `async def` vs `def`, multi-worker deployment, and benchmarking.

```bash
cd 1_fastapi_asgi_uvicorn_granian
uv sync
uv run uvicorn app.main:app --workers 4
uv run granian --interface asgi app.main:app --workers 4
```

---

### 3. Databases & ORMs

#### [2_fastapi_async_orm_sqlmodel_tortoise](./2_fastapi_async_orm_sqlmodel_tortoise)
Task Manager API with Tortoise ORM (primary) and SQLModel (alternative). Includes Aerich migrations and PostgreSQL Docker setup.

```bash
cd 2_fastapi_async_orm_sqlmodel_tortoise
docker compose up db -d
pip install fastapi uvicorn tortoise-orm aiosqlite pydantic-settings pytest pytest-asyncio httpx anyio
uvicorn app.main:app --port 8000
```

#### [3_fastapi_asyncpg_database_driver](./3_fastapi_asyncpg_database_driver)
Product Inventory API using asyncpg with raw SQL and connection pooling. Repository pattern, transactions with savepoints, and SQL migrations.

```bash
cd 3_fastapi_asyncpg_database_driver
docker compose up db -d
pip install "fastapi[standard]" asyncpg pydantic-settings pytest pytest-asyncio httpx anyio
uvicorn app.main:app --port 8000
```

#### [12_cursor_pagination](./12_cursor_pagination)
Keyset (cursor) pagination over 1M-row PostgreSQL table. Opaque base64url cursors, composite indexing, and resumable CSV ingestion.

```bash
cd 12_cursor_pagination
docker compose up -d
uv sync
uv run python -m scripts.ingest
uv run uvicorn app.main:app --port 8000
```

#### [13_fastapi_streaming_chunking](./13_fastapi_streaming_chunking)
Four streaming endpoints with bounded memory: CSV export, NDJSON report, resumable feed, and short-transaction chunking.

```bash
cd 13_fastapi_streaming_chunking
docker compose up -d
uv sync --active
uv run python -m scripts.ingest
uv run uvicorn app.main:app --port 8000
```

#### [14_fastapi_pipeline](./14_fastapi_pipeline)
Composable streaming data pipeline with pluggable Source/Filter/Transform/Sink stages. Reads from PostgreSQL, processes in bounded memory, streams NDJSON/CSV.

```bash
cd 14_fastapi_pipeline
docker compose up -d
uv sync
uv run uvicorn app.main:app --port 8002
```

---

### 4. Validation

#### [4_fastapi_pydantic_v2_validation](./4_fastapi_pydantic_v2_validation)
User Registration API with Pydantic v2: `field_validator`, `model_validator`, `computed_field`, `field_serializer`, discriminated unions, `TypeAdapter`, and nested models.

```bash
cd 4_fastapi_pydantic_v2_validation
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
```

---

### 5. Caching

#### [5_fastapi_redis_cache2](./5_fastapi_redis_cache2)
Product management with 15+ Redis patterns: cache-aside, distributed locks, HyperLogLog, shopping cart hashes, rate limiting, idempotency keys, autocomplete, and Pub/Sub invalidation.

```bash
cd 5_fastapi_redis_cache2
docker compose up -d
uv pip install -e ".[dev]"
uvicorn app.main:app --port 8000
pytest --redis
```

---

#### Redis Pub/Sub — Live WebSocket Fan-Out (`redis_pubsub/`)

[Open the end-to-end guide](redis_pubsub/README.md). Publish JSON over HTTP and deliver it live to every WebSocket subscriber on the same Redis channel. The project includes a browser demo and integration tests that use real Redis.

```bash
cd redis_pubsub
uv sync --frozen
docker compose up -d redis
docker compose exec -T redis redis-cli PING  # Expected: PONG
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` in two browser tabs to test fan-out.

---

## 6. Rate Limiting

#### [7_fastapi_slowapi_rate_limiting](./7_fastapi_slowapi_rate_limiting)
Quotes API with IP-based and API-key-based rate limiting, tiered plans (free/pro/admin), fixed vs moving window strategies, and Redis-backed storage.

```bash
cd 7_fastapi_slowapi_rate_limiting
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
```

---

### 7. Monitoring & Observability

#### [8_fastapi_prometheus_monitoring](./8_fastapi_prometheus_monitoring)
Orders API with prometheus-fastapi-instrumentator, Prometheus scrape config, and pre-built Grafana dashboard with latency percentiles and business metrics.

```bash
cd 8_fastapi_prometheus_monitoring
docker compose up -d
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
# Grafana: http://localhost:3000
```

#### [9_fastapi_loguru_structured_logging](./9_fastapi_loguru_structured_logging)
Payment Events API with Loguru: async-safe `enqueue=True`, structured JSON, request correlation IDs, rotating file logs, and sensitive data masking.

```bash
cd 9_fastapi_loguru_structured_logging
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
```

#### [16_fastapi_logging](./16_fastapi_logging)
End-to-end observability pipeline: Loguru (dev), Structlog (prod JSON), Sentry (crash capture), and Pydantic Logfire (request tracing).

```bash
cd 16_fastapi_logging
uv sync
cp .env.example .env
uv run python main.py
```

---

### 8. Authorization

#### [10_fastapi_casbin_authorization](./10_fastapi_casbin_authorization)
Document Management API with Casbin PERM metamodel: RBAC with role inheritance, ABAC ownership checks, declarative policy files, and `require_permission` dependency factory.

```bash
cd 10_fastapi_casbin_authorization
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
```

---

### 9. HTTP Clients

#### [11_fastapi_httpx](./11_fastapi_httpx)
Weather fan-out API with HTTPX `@asynccontextmanager` lifespan connection pooling and `asyncio.gather` for concurrent requests to 5 cities.

```bash
cd 11_fastapi_httpx
pip install fastapi uvicorn httpx requests pytest pytest-asyncio orjson
uvicorn app.main:app --port 8000
```

---

### 10. Pagination & Streaming

See [12_cursor_pagination](./12_cursor_pagination) and [13_fastapi_streaming_chunking](./13_fastapi_streaming_chunking) above.

---

### 11. Pipelines

See [14_fastapi_pipeline](./14_fastapi_pipeline) above.

---

### 12. Logging & Tracing

#### [15_backgroundjobs_async_parallel_processing](./15_backgroundjobs_async_parallel_processing)

A four-part series on background job patterns, all sharing the 1M-row `order_events` dataset:

| Sub-project | Pattern | Key Tech |
|-------------|---------|----------|
| `01_bg_tasks_audit_logging` | FastAPI `BackgroundTasks` | SQLAlchemy async, asyncpg |
| `02_queue_worker_export` | Queue + Worker | FastAPI + Arq + Redis + Postgres |
| `03_multiprocessing_parquet_export` | CPU-bound chunked writes | `multiprocessing.Pool` + PyArrow |
| `04_idempotent_observable_jobs` | Idempotent + observable jobs | Arq, Redis, structlog, Prometheus |

```bash
cd 15_backgroundjobs_async_parallel_processing/<sub-project>
docker compose up -d
uv sync
```

---

### 13. Conceptual Notes

#### [authentication](./authentication)
Source-only notes reconstructing 8 authentication/authorization workflows: API Key, Session, JWT, Access+Refresh, OAuth2, SSO, SAML vs OIDC.

#### [fastapi_notes](./fastapi_notes)
Self-study curriculum with 16+ markdown files covering SQLAlchemy scaling, background jobs, error handling, monitoring, ORM-to-SQL migration, security, lifespan, and production best practices.

#### [python-notes](./python-notes)
Reference guide for 9 modern Python tools: uv, Ruff, Pydantic, Typer, HTTPX, Tenacity, pytest, Hypothesis, build.

---

### 14. Utilities

#### [utils](./utils)
Shared infrastructure for the 12/13/15 project series:

- `order_events_schema.sql` — Table definition with indexes
- `data/order_events_1m.csv` — 1,000,000-row dataset
- `ingest_order_events.py` — Resumable asyncpg COPY loader
- `order_events_data_overview.md` — Data dictionary and reuse instructions

---

## General Setup

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| uv | Latest | Package manager (preferred) |
| Docker | Latest | PostgreSQL, Redis, Prometheus, Grafana |
| pip | Latest | Fallback package manager |

### Quick Start (Any Project)

```bash
# Navigate to project
cd <project-directory>

# Option A: Using uv (recommended)
uv sync
uv run uvicorn app.main:app --port 8000

# Option B: Using pip
pip install -e ".[dev]"
uvicorn app.main:app --port 8000

# API docs
open http://localhost:8000/docs
```

### Docker Services

Most projects that need PostgreSQL or Redis include a `docker-compose.yml`:

```bash
docker compose up -d          # Start all services
docker compose down           # Stop all services
docker compose logs -f        # Follow logs
```

---

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Framework** | FastAPI, Uvicorn, Granian, Gunicorn |
| **Validation** | Pydantic v2 (pydantic-core, Rust-powered) |
| **Databases** | PostgreSQL, asyncpg, SQLAlchemy 2.0, Tortoise ORM, SQLModel |
| **Caching** | Redis 7, fastapi-cache2 |
| **Queues** | ARQ, Taskiq, Redis |
| **Auth** | Casbin (RBAC/ABAC), JWT concepts |
| **Monitoring** | Prometheus, Grafana, prometheus-fastapi-instrumentator |
| **Logging** | Loguru, Structlog, Sentry SDK, Pydantic Logfire |
| **HTTP Client** | HTTPX (AsyncClient, connection pooling) |
| **Testing** | pytest, pytest-asyncio, httpx (ASGITransport), fakeredis |
| **Processing** | multiprocessing, PyArrow (Parquet) |
| **Packaging** | uv, Ruff, build |

---

## Project Structure

```
fastapi_projects/
├── 0.1_uvloop_service/              # uvloop vs asyncio benchmark
├── 0.2_task_queue_project/           # ARQ task queue (monolith + microservice)
├── 1_fastapi_asgi_uvicorn_granian/   # ASGI server comparison
├── 2_fastapi_async_orm_sqlmodel_tortoise/  # Tortoise ORM + SQLModel
├── 3_fastapi_asyncpg_database_driver/     # asyncpg raw SQL + pooling
├── 4_fastapi_pydantic_v2_validation/      # Pydantic v2 validation
├── 5_fastapi_redis_cache2/           # Redis caching patterns (15+)
├── 6_fastapi_taskiq_background_jobs/ # Taskiq background jobs
├── 7_fastapi_slowapi_rate_limiting/  # Rate limiting (IP + API key)
├── 8_fastapi_prometheus_monitoring/  # Prometheus + Grafana
├── 9_fastapi_loguru_structured_logging/  # Loguru structured logging
├── 10_fastapi_casbin_authorization/  # Casbin RBAC/ABAC
├── 11_fastapi_httpx/                 # HTTPX async client pooling
├── 12_cursor_pagination/             # Keyset pagination (1M rows)
├── 13_fastapi_streaming_chunking/    # Streaming response (bounded memory)
├── 14_fastapi_pipeline/              # Composable data pipeline
├── 15_backgroundjobs_async_parallel_processing/  # 4-part background jobs series
│   ├── 01_bg_tasks_audit_logging/
│   ├── 02_queue_worker_export/
│   ├── 03_multiprocessing_parquet_export/
│   └── 04_idempotent_observable_jobs/
├── 16_fastapi_logging/               # Full observability pipeline
├── authentication/                   # Auth workflow notes (8 patterns)
├── fastapi_notes/                    # Study curriculum (16+ topics)
├── python-notes/                     # Python tooling reference (9 tools)
├── utils/                            # Shared 1M-row dataset + schema
└── README.md                         # This file
```

---

## Key Design Principles

1. **Production over tutorial** — Real services, real data, real failure modes
2. **Isolation** — Each project teaches one concern deeply
3. **Bounded memory** — Streaming and pagination never hold full datasets
4. **Idempotency** — Background jobs use deterministic keys for safe retries
5. **Observability** — Every request gets a correlation ID; every error gets logged
6. **Security** — Authorization is declarative; sensitive data is masked
7. **Testability** — Every project has integration tests with real or faithfully mocked dependencies

---

*This is a living portfolio. Each project is self-contained and can be read, run, and deployed independently.*
