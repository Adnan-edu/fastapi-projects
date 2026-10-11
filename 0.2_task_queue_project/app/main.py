# =====================================================================
# app/main.py - FastAPI application entry point
# =====================================================================
# PURPOSE
# -------
# This is the module passed to uvicorn: `uvicorn app.main:app`. It:
#   1. Defines a `lifespan` async context manager that runs ONCE at
#      startup (init DB, open Redis pool) and ONCE at shutdown (close
#      Redis pool).
#   2. Constructs the `app` FastAPI instance with title/description
#      metadata that Swagger UI displays at /docs.
#   3. Mounts the aggregated router (all sub-routers from app/api/)
#      under the /api/v1 prefix.
#   4. Exposes two convenience endpoints: /health and /.
# =====================================================================

# Used to turn a generator function into a context manager that works
# with the FastAPI `lifespan=` argument.
from contextlib import asynccontextmanager

# Main FastAPI framework class.
from fastapi import FastAPI

# Pool lifecycle helpers — open at startup, close at shutdown.
from app.arq_utils import close_redis_pool, get_redis_pool
# Creates all tables (demo: replace with Alembic in production).
from app.database import init_db
# The aggregated APIRouter that bundles every sub-router under one prefix.
from app.api.router import router


# `@asynccontextmanager` lets us write a single async-generator function
# that handles both startup (code before `yield`) and shutdown (code
# after `yield`). FastAPI calls this once on app boot and once on stop.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP -----------------------------------------------------
    # Build DB schema (CREATE TABLE for every model registered on Base).
    await init_db()
    # Build the singleton ArqRedis pool used to enqueue jobs.
    await get_redis_pool()

    # The `yield` separates startup from shutdown. While yielded, the
    # FastAPI server is serving requests.
    yield

    # --- SHUTDOWN ----------------------------------------------------
    # Close the Redis pool so sockets are released and the worker
    # process can exit cleanly on SIGTERM / SIGINT.
    await close_redis_pool()


# Instantiate the FastAPI application. The metadata below is purely
# documentation that surfaces in the OpenAPI schema (/docs, /redoc).
app = FastAPI(
    title="Task Queue API",
    description=(
        "A FastAPI application demonstrating ARQ task queue integration. "
        "Supports both monolithic and microservice deployment patterns. "
        "ARQ features: basic enqueue, job uniqueness (_job_id), deferred execution "
        "(_defer_by, _defer_until), Retry with backoff, cron jobs, task chaining, "
        "fan-out patterns, and WorkerSettings with on_startup/on_shutdown."
    ),
    version="1.0.0",
    # Hook our lifespan function in. FastAPI calls it during the
    # ASGI lifespan protocol (startup + shutdown events).
    lifespan=lifespan,
)

# Mount every route under /api/v1 — that prefix is applied on top of
# the per-router prefixes (e.g. /users, /payments), giving final paths
# like /api/v1/users/ and /api/v1/payments/process.
app.include_router(router, prefix="/api/v1")


# Lightweight health-check used by Docker/K8s probes. Returning 200 OK
# is sufficient to tell the orchestrator "this pod is alive".
@app.get("/health")
async def health():
    return {"status": "healthy"}


# Root index: returns a human-friendly summary plus pointers to docs
# and a list of ARQ features the project demonstrates.
@app.get("/")
async def root():
    return {
        "app": "Task Queue API",
        "version": "1.0.0",
        "docs": "/docs",
        "arq_features": [
            "Basic enqueue",
            "Job uniqueness (_job_id)",
            "Deferred execution (_defer_by, _defer_until)",
            "Retry with exponential backoff",
            "Cron jobs (@cron decorator)",
            "Task chaining & fan-out",
            "Worker lifecycle hooks (on_startup/on_shutdown)",
            "Multiple queue isolation (microservice mode)",
        ],
    }
