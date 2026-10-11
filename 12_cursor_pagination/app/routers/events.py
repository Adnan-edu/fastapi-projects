"""Cursor-paginated `/events` endpoint.

The big idea
============
Pagination has two common shapes:

  A) OFFSET / LIMIT — "give me page 17, with 50 per page"
  B) Keyset (cursor) — "give me the 50 rows that come after this bookmark"

Both look similar from outside, but their cost profiles are radically different.

Why OFFSET becomes slow
-----------------------
A query like

    SELECT * FROM order_events
    ORDER BY created_at, id
    OFFSET 900000 LIMIT 50

forces PostgreSQL to **walk and discard** the first 900,000 rows before
returning any. That's a linear cost in page depth. At 1M rows it's tens of ms;
at 50M rows the planner often abandons the index and falls back to a sequential
scan + sort. The deeper your users page, the slower the API gets — death by
infinite scroll.

Why keyset stays fast forever
-----------------------------
With a composite index on `(created_at, id)` and the row-value comparison

    WHERE (created_at, id) > (:cur_created_at, :cur_id)
    ORDER BY created_at, id
    LIMIT :limit + 1

PostgreSQL does a single B-tree **seek** to the cursor's exact position, then a
forward scan of exactly `limit + 1` index entries. Cost is **O(log N)** for the
seek and **O(limit)** for the read — independent of how deep you are in the
table. Page 1 and page 20,000 cost the same.

We verified this empirically: on a 1M-row table, keyset stayed at ~2 ms while
the deep-OFFSET equivalent took ~40 ms with a parallel seq-scan + sort. See
README §"EXPLAIN ANALYZE".

The `+ 1` trick
---------------
We ask for one more row than the client wants. If we get back `limit + 1`, we
know there's at least one more row beyond this page — so `has_more = True` and
we return a `next_cursor`. If we get back `<= limit` rows, this is the last
page. This is cheaper than a separate `SELECT COUNT(*)`, which would have to
scan the whole filtered set on every request.

Why a row-value comparison and not `created_at > :c OR (created_at = :c AND id > :i)`?
-------------------------------------------------------------------------------------
They are *logically* equivalent, but the row-value form `(a, b) > (x, y)`:
1. Is shorter and harder to misread,
2. Maps directly to the way the B-tree index is ordered, and
3. The planner reliably translates it into a single index seek with the
   condition `Index Cond: (ROW(created_at, id) > ROW(...))`.

You can confirm this in `EXPLAIN ANALYZE` — the plan node is `Index Scan using
ix_order_events_created_at_id`, not a `BitmapOr`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.cursor import Cursor
from app.db import get_session
from app.models import OrderEvent
from app.schemas import EventsPage, OrderEventOut

# APIRouter lets us group related routes under a common `/events` prefix and
# OpenAPI tag without polluting `app.main`. `main.py` mounts this with
# `app.include_router(events.router)`.
router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventsPage, summary="List events (cursor paginated)")
async def list_events(
    # ---- Query params -----------------------------------------------------
    # `cursor` is the opaque bookmark from a previous response. None on the
    # first page. We don't validate its content here — `Cursor.decode` does
    # that and turns malformed input into a clean 400.
    cursor: str | None = Query(default=None, description="Opaque cursor from previous page."),
    # `limit` is the requested page size. `ge=1` lets FastAPI reject `limit=0`
    # automatically with a 422 — we never see that case in our code.
    # We don't enforce an upper bound at the FastAPI level because we want a
    # *silent clamp* (the server caps oversized requests instead of erroring).
    # That's gentler for clients and protects the DB from accidental huge pages.
    limit: int | None = Query(default=None, ge=1, description="Page size (server-capped)."),
    # Optional secondary filter. Aliased so the URL stays human-friendly
    # (`?status=paid`) while the Python parameter avoids shadowing the
    # `status` import from `fastapi`.
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Optional status filter (e.g. paid, pending).",
    ),
    # ---- Dependencies -----------------------------------------------------
    # `get_session` yields an AsyncSession from the session factory created in
    # the lifespan. FastAPI handles the context-manager lifecycle: open before
    # the handler runs, close after the response is sent. One session per
    # request — never share sessions across requests.
    session: AsyncSession = Depends(get_session),
    # `get_settings` is `@lru_cache`d so this is effectively a singleton.
    # Injecting it (instead of importing the module-level instance) makes the
    # route trivially testable with `app.dependency_overrides`.
    settings: Settings = Depends(get_settings),
) -> EventsPage:
    # ---- 1. Resolve effective page size -----------------------------------
    # Two-layer policy:
    #   - If the client omits `limit`, use the configured default.
    #   - Whatever they ask for, never exceed `max_page_limit`.
    # The silent clamp matters because a single `?limit=1000000` request could
    # otherwise OOM the worker. Defending the DB is the API's job.
    effective_limit = min(limit or settings.default_page_limit, settings.max_page_limit)

    # ---- 2. Build the base query -----------------------------------------
    # `select(OrderEvent)` returns a SQLAlchemy 2.0 Select statement; nothing
    # has hit the database yet. We chain `.where(...)` / `.order_by(...)` to
    # progressively shape the SQL before executing it once at the bottom.
    #
    # The ORDER BY here is what makes the query deterministic. It MUST match
    # the leading columns of the composite index `(created_at, id)` — that's
    # the only way PostgreSQL can return rows in this order without sorting.
    stmt = select(OrderEvent).order_by(OrderEvent.created_at, OrderEvent.id)

    # ---- 3. Apply the cursor condition (if any) --------------------------
    if cursor is not None:
        # Decode raises HTTPException(400) on garbage input — caller gets a
        # clean error and we never construct an invalid query.
        c = Cursor.decode(cursor)
        # The keyset predicate. `tuple_(a, b) > (x, y)` compiles to PostgreSQL's
        # row-value comparison `(a, b) > (x, y)`, which the planner can
        # combine with the composite index to do a single B-tree seek to the
        # cursor position. Without this, we'd be back to a full sort.
        stmt = stmt.where(
            tuple_(OrderEvent.created_at, OrderEvent.id) > (c.created_at, c.id)
        )

    # ---- 4. Apply optional filters ---------------------------------------
    # Filters compose with the cursor predicate — both are `AND`ed into the
    # WHERE clause. Note: with a status filter, the composite `(created_at, id)`
    # index still does the seek, but the planner may then have to scan past
    # rows that match the cursor range but not the status. For very selective
    # filters consider an index on `(status, created_at, id)`.
    if status_filter is not None:
        stmt = stmt.where(OrderEvent.status == status_filter)

    # ---- 5. The `LIMIT + 1` trick ----------------------------------------
    # Ask for one more row than we'll return. If the DB gives us `limit + 1`
    # rows, we know there's at least one more after the page — so `has_more`
    # is True and we should mint a `next_cursor`. If it gives us `<= limit`,
    # this is the last page. No COUNT(*) needed.
    stmt = stmt.limit(effective_limit + 1)

    # ---- 6. Execute -------------------------------------------------------
    # This is the single round-trip to PostgreSQL. `session.execute` runs the
    # statement; `.scalars()` unwraps the single-entity result rows (each row
    # is a 1-tuple containing an `OrderEvent` instance); `.all()` materialises
    # them into a list. For a `limit + 1` of at most 501 rows this is fine.
    # For huge "export" endpoints, prefer `session.stream()` with an async for.
    result = await session.execute(stmt)
    rows = result.scalars().all()

    # ---- 7. Compute pagination metadata ----------------------------------
    # If we got the extra row back, drop it: clients should see exactly the
    # page size they asked for, not page+1. The dropped row's predecessor
    # (the actual last item on this page) is what we use to mint the next
    # cursor — that way a client can resume exactly after this page.
    has_more = len(rows) > effective_limit
    page = rows[:effective_limit]

    # ---- 8. Mint the next cursor -----------------------------------------
    # Only when there *is* a next page. On the terminal page we return
    # `next_cursor: null` to signal end-of-stream. We use the last row of the
    # *trimmed* page (not the discarded probe row); the next request will use
    # `(created_at, id) > (this.created_at, this.id)` to pick up immediately
    # after it. That's why the index requires both columns: without `id`,
    # two rows sharing `created_at` would collide on the cursor position.
    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = Cursor(created_at=last.created_at, id=last.id).encode()

    # ---- 9. Serialize ----------------------------------------------------
    # `OrderEventOut.model_validate(r)` uses Pydantic v2's `from_attributes=True`
    # (set on the schema's `model_config`) to read attributes off the ORM
    # instance — no manual `.dict()` or column-by-column copy. Pydantic also
    # handles type coercion (e.g. `Decimal` → JSON-safe string) at this step.
    return EventsPage(
        items=[OrderEventOut.model_validate(r) for r in page],
        next_cursor=next_cursor,
        has_more=has_more,
    )
