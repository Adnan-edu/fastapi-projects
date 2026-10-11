"""Streaming endpoints.

The package is split by *use case* rather than by mechanism, because the
endpoints answer different questions:

- `export`   — "give me a subset of rows as a downloadable file"
- `report`   — "summarise millions of rows without holding them in memory"
- `feed`     — "push events to a downstream consumer as a long-lived stream"
- `chunked`  — "stream events without holding one long DB transaction open"

They share the same building blocks (async generators, constant-memory
iteration) but differ in DB shape: `export`/`report`/`feed` use a single
server-side cursor; `chunked` uses many short keyset-paged transactions.
"""

from fastapi import APIRouter

from app.streaming.chunked import router as chunked_router
from app.streaming.export import router as export_router
from app.streaming.feed import router as feed_router
from app.streaming.report import router as report_router

router = APIRouter(prefix="/stream", tags=["streaming"])
router.include_router(export_router)
router.include_router(report_router)
router.include_router(feed_router)
router.include_router(chunked_router)

__all__ = ["router"]
