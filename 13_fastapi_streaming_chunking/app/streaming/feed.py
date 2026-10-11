"""Use case #3 — Feed downstream systems.

What "feed" means here
----------------------
A downstream consumer (a worker, an ETL job, another microservice) wants
order events one at a time and reacts to each one independently. They don't
want a paginated JSON response with `next_cursor`; they want a long-lived HTTP
connection that emits one record per line until either side decides to stop.

This is the same shape as Kafka's consumer protocol over HTTP — minus the
delivery guarantees. For at-least-once semantics, you'd add a per-record
acknowledgement cursor the consumer echoes back; that's out of scope for this
demo but the streaming machinery is identical.

NDJSON, not SSE
---------------
We use NDJSON for the same reason the report does: it's a parse-as-you-go
format that works with any HTTP client. Server-Sent Events would also work,
but SSE bakes in event-type framing and reconnect semantics that downstream
ETL tooling typically doesn't want.

Backpressure
------------
Async generators in Starlette respect TCP backpressure: if the client stops
reading, the `yield` blocks, which suspends our `async for`, which stops
pulling from the DB cursor. Memory stays bounded by `chunk_size` no matter how
slow the consumer is.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import OrderEvent
from app.streaming._common import iter_rows

router = APIRouter()


def _serialize(row: OrderEvent) -> dict:
    """Project an ORM row to the shape we expose to downstream consumers.

    Kept as a plain dict (not Pydantic) because we're emitting many millions
    of rows and the per-row serialisation cost matters. Pydantic v2 is fast,
    but a hand-written dict + `default=str` for Decimal/datetime is faster
    still and the schema here is small and stable.
    """
    return {
        "id": row.id,
        "order_id": row.order_id,
        "customer_id": row.customer_id,
        "event_type": row.event_type,
        "status": row.status,
        "amount": str(row.amount),
        "currency": row.currency,
        "country": row.country,
        "payment_method": row.payment_method,
        "product_sku": row.product_sku,
        "quantity": row.quantity,
        "created_at": row.created_at.isoformat(),
        "metadata": row.metadata_,
    }


@router.get(
    "/feed.ndjson",
    summary="Stream a continuous feed of order events as NDJSON",
    response_class=StreamingResponse,
)
async def stream_feed(
    after_id: int | None = Query(
        default=None,
        ge=0,
        description="Resume the feed strictly after this id. Use the last id you saw.",
    ),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(
        default=None,
        ge=1,
        description="Optional hard cap for testing. Production consumers leave this unset.",
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    # Order by `id` alone here (not `(created_at, id)`) because downstream
    # consumers resume by id and the primary key already guarantees a total
    # order — no need to drag created_at into the cursor.
    stmt = select(OrderEvent).order_by(OrderEvent.id)
    if after_id is not None:
        stmt = stmt.where(OrderEvent.id > after_id)
    if status_filter is not None:
        stmt = stmt.where(OrderEvent.status == status_filter)

    # `limit` here only exists for demos/tests; production feeds run until
    # the client disconnects. We honour `stream_max_rows` as a safety belt too.
    effective_max = limit if limit is not None else settings.stream_max_rows

    async def feed_stream() -> AsyncIterator[bytes]:
        async for row in iter_rows(
            session,
            stmt,
            chunk_size=settings.stream_chunk_size,
            max_rows=effective_max,
        ):
            # Bytes, not str: skips the implicit str->bytes encoding hop that
            # Starlette would otherwise do on every yield. At millions of rows
            # this is measurable.
            yield (json.dumps(_serialize(row)) + "\n").encode("utf-8")

    return StreamingResponse(
        feed_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )
