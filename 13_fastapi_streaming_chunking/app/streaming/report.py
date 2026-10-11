"""Use case #2 — Generate a comprehensive report over millions of rows.

Two ideas in one endpoint
-------------------------
Reports are interesting because they're a hybrid: the *aggregate numbers* must
be computed across the whole dataset, but the consumer wants to start seeing
*something* immediately. We solve this by streaming the report in stages:

  1. A `meta` event the moment we open the response — "report started".
  2. Per-status (or per-country) running aggregates, emitted as we sweep.
  3. A final `summary` event with the totals.

Each stage is one NDJSON line (newline-delimited JSON). NDJSON is the
streaming-report format: every line is a valid JSON object, so a consumer can
parse it incrementally without ever needing to know the total size.

Why not just do GROUP BY in SQL and return the result?
------------------------------------------------------
You absolutely could, and for *just* the aggregates that would be the right
call. The point of this endpoint is to demonstrate the streaming *pattern* you
need when the report itself doesn't fit in memory — e.g. when it includes
sample rows, anomaly callouts, or per-bucket histograms that grow with the
dataset. The accumulator below is a stand-in for that more complex shape.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import OrderEvent
from app.streaming._common import iter_rows

router = APIRouter()


def _ndjson(payload: dict) -> str:
    """Serialize one record as a single NDJSON line.

    `default=str` handles Decimal and datetime without forcing the caller to
    pre-convert. The trailing newline is what makes the format streamable.
    """
    return json.dumps(payload, default=str) + "\n"


@router.get(
    "/report.ndjson",
    summary="Stream a multi-stage report as NDJSON",
    response_class=StreamingResponse,
)
async def stream_report(
    status_filter: str | None = Query(default=None, alias="status"),
    progress_every: int = Query(
        default=50_000,
        ge=1_000,
        description="Emit a progress line every N scanned rows.",
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    stmt = select(OrderEvent).order_by(OrderEvent.created_at, OrderEvent.id)
    if status_filter is not None:
        stmt = stmt.where(OrderEvent.status == status_filter)

    async def report_stream() -> AsyncIterator[str]:
        # 1. Header — tells the consumer the report has started and what
        #    knobs were applied. Sending this first lights up a progress UI
        #    immediately instead of leaving the client guessing.
        yield _ndjson(
            {
                "type": "meta",
                "started_at": datetime.now(UTC).isoformat(),
                "filters": {"status": status_filter},
                "progress_every": progress_every,
            }
        )

        # 2. Sweep — accumulate per-status totals and emit periodic progress.
        #    We keep counts and amounts in two parallel defaultdicts so the
        #    per-row update is two cheap dict ops and no type-coercion. At
        #    millions of rows, avoiding `int(...) + 1` / `Decimal(...) + x`
        #    inside the loop is a measurable win. `amount` is NUMERIC(12,2)
        #    so we stay in Decimal end-to-end to preserve precision.
        total_rows = 0
        total_amount = Decimal("0")
        count_by_status: dict[str, int] = defaultdict(int)
        amount_by_status: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        async for row in iter_rows(
            session,
            stmt,
            chunk_size=settings.stream_chunk_size,
            max_rows=settings.stream_max_rows,
        ):
            total_rows += 1
            total_amount += row.amount
            count_by_status[row.status] += 1
            amount_by_status[row.status] += row.amount

            if total_rows % progress_every == 0:
                # Progress lines keep the connection warm and give the client
                # something to render. Critical for very long reports — without
                # them, a load balancer may decide the stream is dead.
                yield _ndjson(
                    {
                        "type": "progress",
                        "rows_scanned": total_rows,
                        "running_total_amount": total_amount,
                    }
                )

        # 3. Summary — the final totals. Always emitted last; consumers that
        #    only care about aggregates can ignore everything before this line.
        yield _ndjson(
            {
                "type": "summary",
                "rows_scanned": total_rows,
                "total_amount": total_amount,
                "by_status": {
                    status: {
                        "count": count_by_status[status],
                        "amount": amount_by_status[status],
                    }
                    for status in count_by_status
                },
                "finished_at": datetime.now(UTC).isoformat(),
            }
        )

    return StreamingResponse(
        report_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )
