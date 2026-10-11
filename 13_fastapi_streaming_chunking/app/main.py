"""FastAPI entrypoint for the streaming demo.

We mount three routers:
  - /healthz, /readyz   liveness + DB readiness
  - /stream/*           the streaming endpoints (export, report, feed)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import dispose_engine, init_engine
from app.routers import health
from app.streaming import router as streaming_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    yield
    await dispose_engine()


app = FastAPI(
    title="Large Responses Must Be Streamed",
    description=(
        "Companion to the cursor-pagination project. Demonstrates streaming "
        "for the three places where a giant JSON list would be the wrong tool: "
        "exports, reports, and downstream feeds."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(streaming_router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": "fastapi-streaming",
        "docs": "/docs",
        "export_csv": "/stream/export.csv",
        "report_ndjson": "/stream/report.ndjson",
        "feed_ndjson": "/stream/feed.ndjson",
    }
