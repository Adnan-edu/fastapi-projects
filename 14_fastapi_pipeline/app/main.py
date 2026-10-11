"""FastAPI app entrypoint.

This file does three jobs and nothing else:

1. Define the lifespan — what happens at startup and shutdown.
2. Instantiate the FastAPI application.
3. Mount routers and expose a discoverability `/` endpoint.

Routing logic lives in the routers; pipeline logic lives in the pipeline/
package; settings logic lives in app/config.py. Keeping main.py thin makes
it easy to reason about the app's surface area.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import dispose_engine, init_engine
from app.routers import health, pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook.

    The pattern is:
        startup code
        yield                  # ← app is running, requests are served here
        shutdown code

    Anything before `yield` runs once when the first worker boots; anything
    after `yield` runs once when the process is asked to shut down.

    We initialize the engine BEFORE yielding so the very first request can
    use it, and dispose AFTER yielding so in-flight requests finish before
    we tear connections down.
    """
    init_engine()
    yield
    await dispose_engine()


# FastAPI app instance. `lifespan=` is the modern (Starlette ≥ 0.27) way to
# wire startup/shutdown — older `@app.on_event("startup")` decorators still
# work but are deprecated.
app = FastAPI(
    title="FastAPI Data Pipeline",
    description=(
        "Composable streaming pipeline: Database -> Filter -> Chunk -> "
        "Transform -> Stream -> Client. Each stage is independently "
        "swappable and runs in bounded memory."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Routers are mounted at their declared prefixes (health has none;
# pipeline has prefix="/pipeline"). Adding a new endpoint family is a new
# router file + one include_router call here.
app.include_router(health.router)
app.include_router(pipeline.router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Tiny index for humans hitting the bare host. Points them at the
    interactive Swagger UI and the demo endpoint so they can self-discover.
    Not part of the contract — feel free to remove in production.
    """
    return {
        "name": "fastapi-pipeline",
        "docs": "/docs",
        "demo": "/pipeline/run.ndjson",
    }
