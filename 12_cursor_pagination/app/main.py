"""FastAPI entrypoint.

The lifespan context manager owns the lifetime of the async engine: created
once at startup, disposed at shutdown. This is the modern replacement for the
deprecated `@app.on_event("startup"/"shutdown")` pair.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import dispose_engine, init_engine
from app.routers import events, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    yield
    await dispose_engine()


app = FastAPI(
    title="Cursor-Based Pagination",
    description=(
        "Educational reference implementation of keyset (cursor) pagination "
        "over a 1M-row PostgreSQL table."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(events.router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": "cursor-pagination",
        "docs": "/docs",
        "events": "/events",
    }
