"""The demo endpoint — `GET /pipeline/run.ndjson`.

This file is the bridge between the HTTP world and the pipeline world.
Everything below this point in the call stack is pure async-Python; nothing
above this point knows or cares about pipelines.

Contract
--------
GET /pipeline/run.ndjson
  ?after_id=0          Keyset cursor for resumption.
  &status=paid         Optional. Becomes a SQL WHERE on OrderEvent.status.
  &min_amount=100      Optional. Becomes a Python-side PredicateFilter.
  &chunk_size=1000     Overrides PIPELINE_CHUNK_SIZE for this request.
  &limit=10000         Optional cap on rows pulled from the DB.

The handler:
1. Reads query params and builds the pipeline shape from them.
2. Wraps `pipeline.run()` in `_safe_stream` so a mid-stream StageError
   becomes a trailing error NDJSON line instead of a 500.
3. Returns a StreamingResponse with the right content-type and the
   `X-Accel-Buffering: no` header so reverse proxies don't accumulate the
   body before flushing.
"""

import json
from collections.abc import AsyncIterator
from decimal import Decimal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import OrderEvent
from pipeline.core import Pipeline
from pipeline.errors import StageError
from pipeline.stages import DbKeysetSource, NdjsonSink, PredicateFilter, Projection

# All endpoints in this file are nested under /pipeline. The tag groups
# them in the Swagger UI.
router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# Fixed projection for the demo endpoint. Keeping this at module scope
# (not inside the handler) makes the API contract self-documenting — to
# see what columns the demo returns, you look at this constant.
PROJECTION_FIELDS = ("id", "order_id", "amount", "status", "country", "created_at")


@router.get("/run.ndjson", summary="Run the demo pipeline and stream NDJSON")
async def run_ndjson(
    # FastAPI Query() does parameter validation. `ge=0` rejects negative
    # values at the framework layer — they never reach the handler.
    after_id: int = Query(0, ge=0),
    status: str | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    # `le=100_000` puts an upper bound on chunk_size — without it, a
    # malicious or careless `chunk_size=10_000_000` would try to allocate
    # ten million rows in one query.
    chunk_size: int | None = Query(None, ge=1, le=100_000),
    limit: int = Query(0, ge=0),
) -> StreamingResponse:
    settings = get_settings()
    # Per-request override falls back to the env-default if the caller
    # didn't specify. `or` works here because chunk_size=0 is rejected by
    # the validator and limit=0 means "unbounded" which is also the env
    # default.
    effective_chunk = chunk_size or settings.pipeline_chunk_size
    effective_limit = limit or settings.pipeline_max_rows

    # --- Build the SQL-pushdown filters
    # Anything we can express as a WHERE goes here; the DB does the work
    # and non-matching rows never cross the network.
    where_clauses = []
    if status:
        where_clauses.append(OrderEvent.status == status)

    # --- Build the Python-side stage chain
    # We assemble a list of stages, conditionally inserting PredicateFilter
    # if the caller gave a min_amount. This is the pattern for building a
    # pipeline shape from runtime configuration.
    stages = []
    if min_amount is not None:
        # `Decimal(str(min_amount))` is the correct float→Decimal route.
        # Going through str avoids inheriting float's binary
        # imprecision (e.g. Decimal(0.1) → 0.10000000000000000555…).
        threshold = Decimal(str(min_amount))
        # Default-argument trick captures `threshold` by value at lambda
        # creation time, so the predicate is stable even if `threshold`
        # is later rebound.
        stages.append(
            PredicateFilter(lambda row, t=threshold: row.amount >= t, name="min_amount")
        )
    # Projection always runs; it normalizes the ORM row into a dict that
    # the sink can serialize.
    stages.append(Projection(PROJECTION_FIELDS))
    # NdjsonSink is the terminal stage — it emits bytes from here on.
    stages.append(NdjsonSink())

    # --- Compose
    pipeline = Pipeline(
        DbKeysetSource(
            get_sessionmaker(),
            chunk_size=effective_chunk,
            after_id=after_id,
            where_clauses=where_clauses,
            max_rows=effective_limit,
        ),
        *stages,
    )

    # `StreamingResponse` expects an async iterator of bytes. `_safe_stream`
    # gives us that, plus the StageError-to-trailer-line conversion.
    return StreamingResponse(
        _safe_stream(pipeline),
        media_type="application/x-ndjson",
        headers={
            # `X-Accel-Buffering: no` tells nginx (and compatible proxies)
            # not to buffer the response. Without it, the proxy collects
            # the whole body before forwarding, defeating the streaming.
            "X-Accel-Buffering": "no",
        },
    )


async def _safe_stream(pipeline: Pipeline) -> AsyncIterator[bytes]:
    """Convert mid-stream StageError into a trailing NDJSON error line.

    Why not just let the exception propagate?
    -----------------------------------------
    Once a StreamingResponse has started sending bytes to the client,
    Starlette has already written HTTP headers including a 200 status.
    Raising at that point causes Starlette to close the connection
    abruptly — the client sees a truncated body with no error context.
    From the client's perspective, that's indistinguishable from a network
    blip.

    By catching StageError inside the generator and emitting a structured
    final line, we give the client an observable, machine-readable signal
    of failure: an extra NDJSON line with `"type":"error"`. Tools like
    `jq` and pandas can detect this and surface it, where a truncated
    body would just look like fewer rows.
    """
    try:
        async for chunk in pipeline.run():
            yield chunk
    except StageError as e:
        # Structured trailer line. Consumers should always check the last
        # parsed object for `"type":"error"` — it's the only honest way
        # to know whether a streaming export completed.
        payload = {
            "type": "error",
            "stage": e.stage_name,
            "detail": repr(e.cause),
        }
        yield (json.dumps(payload) + "\n").encode("utf-8")
