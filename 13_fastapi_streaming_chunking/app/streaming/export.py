"""Use case #1 — Export a subset of data as CSV.

Why CSV?
--------
CSV is the lingua franca of data exports: spreadsheets, BI tools, and ad-hoc
analyses all consume it natively. It also happens to be the easiest format to
stream — there's no closing bracket to worry about, every row is self-contained,
and the client can start parsing as soon as the first chunk arrives.

The streaming contract
----------------------
We return a `StreamingResponse` whose body is an async generator. Each `yield`
becomes a TCP write. The generator never holds more than `chunk_size` rows in
memory at once, so this endpoint works the same on 1k rows or 50M.

Filtering
---------
`status` and `country` filters compose with the streamed scan. With a selective
filter (e.g. `status=paid`) the planner may use the `ix_order_events_status`
index. Without filters, this is a straight ordered scan of the composite
`(created_at, id)` index — same shape as the cursor-pagination project.
"""

from __future__ import annotations

import csv
import io
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


# The CSV column order doubles as the contract for downstream consumers, so we
# define it once at module scope. Changing this is a breaking change.
CSV_COLUMNS = (
    "id",
    "order_id",
    "customer_id",
    "event_type",
    "status",
    "amount",
    "currency",
    "country",
    "payment_method",
    "product_sku",
    "quantity",
    "created_at",
    "metadata",
)


@router.get(
    "/export.csv",
    summary="Stream a CSV export of order events",
    response_class=StreamingResponse,
)
async def export_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    country: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    # Build the query lazily — no I/O yet. ORDER BY matches the composite index
    # so PostgreSQL streams rows out in index order without a sort step.
    stmt = select(OrderEvent).order_by(OrderEvent.created_at, OrderEvent.id)
    if status_filter is not None:
        stmt = stmt.where(OrderEvent.status == status_filter)
    if country is not None:
        stmt = stmt.where(OrderEvent.country == country)

    async def csv_stream() -> AsyncIterator[str]:
        # Reuse a single `StringIO` + `csv.writer` for the whole response rather
        # than constructing them per row. `csv.writer.writerow` handles quoting,
        # escaping, and the trailing newline correctly — doing it by hand with
        # f-strings is a classic source of broken exports when a field contains
        # a comma or quote.
        buf = io.StringIO()
        writer = csv.writer(buf)

        def take_line() -> str:
            line = buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            return line

        # Header first, then a row at a time. The header is essential because
        # consumers may save the file directly to disk and re-open it later
        # without context.
        writer.writerow(CSV_COLUMNS)
        yield take_line()

        async for row in iter_rows(
            session,
            stmt,
            chunk_size=settings.stream_chunk_size,
            max_rows=settings.stream_max_rows,
        ):
            writer.writerow(
                (
                    row.id,
                    row.order_id,
                    row.customer_id,
                    row.event_type,
                    row.status,
                    f"{row.amount:.2f}",
                    row.currency,
                    row.country,
                    row.payment_method,
                    row.product_sku,
                    row.quantity,
                    row.created_at.isoformat(),
                    row.metadata_ or "",
                )
            )
            yield take_line()

    return StreamingResponse(
        csv_stream(),
        media_type="text/csv",
        headers={
            # `attachment` tells the browser to download rather than render.
            # The filename is just a hint; servers behind a CDN should ensure
            # it doesn't leak any sensitive context.
            "Content-Disposition": 'attachment; filename="order_events.csv"',
            # Hint to intermediaries: don't try to buffer this whole response.
            "X-Accel-Buffering": "no",
        },
    )
