"""Use case #4 — Chunk everything (even when streaming).

The other streaming endpoints in this package hold one server-side cursor
open for the entire response. That's the right shape for many workloads, but
it has a real cost: one database transaction stays open for as long as the
client keeps reading. On a slow consumer that can be minutes or hours, and
during that time the connection holds locks, accumulates dead-tuple visibility
state, and counts against `idle_in_transaction_session_timeout`.

The chunking pattern flips that trade-off. Instead of one long transaction
walking a cursor, we issue many short `SELECT ... WHERE id > :last_id LIMIT N`
queries, each in its own transaction. The response is still streamed — bytes
go out the moment the first chunk arrives — but on the database side we look
like a series of bounded keyset reads, not one open-ended scan.

What chunking buys you
----------------------
* **Short transactions.** Each chunk opens, fetches, and closes. No lock is
  held for longer than it takes to read `CHUNK_SIZE` rows.
* **Failure recovery.** If something blows up mid-stream, the client knows
  the last `id` it saw — replaying is `?after_id=<last_id>` and you're back
  in business. Compare that to a torn server-side cursor, which has no
  resumable identity from the consumer's side.
* **Controlled memory growth.** Memory per chunk is exactly `CHUNK_SIZE`
  rows; we never accumulate across chunks.

Why this is a different endpoint, not a flag on the others
----------------------------------------------------------
The shape of the database work is genuinely different — many short reads vs.
one long cursor — and the operational characteristics (lock duration,
restartability, observability) follow from that. Keeping them as separate
endpoints makes the trade-off explicit at the URL, which is exactly where
operators look when something goes wrong at 3am.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app import db as db_module
from app.config import Settings, get_settings
from app.models import OrderEvent

router = APIRouter()


def _serialize(row: OrderEvent) -> dict:
    """Project an ORM row to the wire shape.

    Same projection as the feed endpoint — kept as a plain dict (not Pydantic)
    so the per-row cost stays low across millions of rows.
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
    "/chunked.ndjson",
    summary="Stream order events using many short keyset-paged transactions",
    response_class=StreamingResponse,
)
async def stream_chunked(
    after_id: int = Query(
        default=0,
        ge=0,
        description="Resume the stream strictly after this id. Pass the last id you saw.",
    ),
    status_filter: str | None = Query(default=None, alias="status"),
    chunk_size: int | None = Query(
        default=None,
        ge=1,
        le=500_000,
        description="Rows per chunk. Defaults to STREAM_CHUNK_SIZE.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        description="Optional hard cap on rows served. Production consumers leave this unset.",
    ),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    # Deliberately not using `Depends(get_session)` here: that would open one
    # session for the whole response, which is exactly the property we're
    # trying to avoid. We open a fresh session per chunk inside the generator.
    if db_module._sessionmaker is None:
        raise RuntimeError("Database engine not initialized. Did lifespan run?")
    sessionmaker = db_module._sessionmaker

    effective_chunk_size = chunk_size or settings.stream_chunk_size
    effective_max = limit if limit is not None else settings.stream_max_rows

    async def chunked_stream() -> AsyncIterator[bytes]:
        last_id = after_id
        served = 0

        while True:
            # One short transaction per chunk. The `async with` exits — and
            # the transaction commits — before we yield the rows downstream,
            # which is the whole point of the pattern: we never hold a DB
            # connection while we wait on the client.
            async with sessionmaker() as session:
                stmt = (
                    select(OrderEvent)
                    .where(OrderEvent.id > last_id)
                    .order_by(OrderEvent.id)
                    .limit(effective_chunk_size)
                )
                if status_filter is not None:
                    stmt = stmt.where(OrderEvent.status == status_filter)

                result = await session.execute(stmt)
                rows = result.scalars().all()

            if not rows:
                # Empty chunk = end of data. We don't keep polling; this is a
                # finite stream, not a tail. A consumer that wants tailing
                # behaviour can reconnect with the last id it saw.
                break

            for row in rows:
                yield (json.dumps(_serialize(row)) + "\n").encode("utf-8")
                served += 1
                if effective_max and served >= effective_max:
                    return

            # Advance the keyset cursor. Because we ORDER BY id and filter
            # WHERE id > last_id, the next chunk picks up exactly where this
            # one left off — no gaps, no overlaps, no offset arithmetic.
            last_id = rows[-1].id

            # If the DB returned a partial chunk it means we've drained the
            # table; skip the next round-trip.
            if len(rows) < effective_chunk_size:
                break

    return StreamingResponse(
        chunked_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )
