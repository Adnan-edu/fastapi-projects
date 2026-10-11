"""Shared streaming primitives.

The single most important idea in this module is `iter_rows`: a generator that
walks a `SELECT` statement in **server-side cursor windows**, so memory stays
flat regardless of how many rows the query matches.

Why we don't just do `await session.execute(stmt)` + iterate
------------------------------------------------------------
A plain `execute(...).scalars().all()` materialises the entire result set in
memory before we ever yield the first byte to the client. That's exactly the
"giant JSON list" failure mode this app is designed to avoid.

`session.stream(stmt)` returns an `AsyncResult` backed by a server-side cursor.
We iterate it with `async for`, and SQLAlchemy fetches rows in batches under
the hood — controlled here by `yield_per(chunk_size)`. Memory is bounded by
`chunk_size`, not by the total row count.

Why an Optional row-count cap
-----------------------------
`stream_max_rows` exists so a misconfigured client or runaway query can't pin a
DB connection for an hour. The cap is enforced in Python after the seek, which
is fine — keyset paging plus an early `break` is still O(rows-served), never
O(table size).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


async def iter_rows(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    chunk_size: int,
    max_rows: int = 0,
) -> AsyncIterator[Any]:
    """Yield ORM rows from `stmt` using a server-side cursor.

    Args:
        session:    Open AsyncSession (kept open for the lifetime of the stream).
        stmt:       A SQLAlchemy 2.0 Select. Must have a deterministic ORDER BY
                    if you care about row order across the stream.
        chunk_size: How many rows the DB driver fetches per round-trip. Tuning
                    knob: bigger = fewer round-trips, more memory per chunk.
        max_rows:   Hard cap. 0 means unbounded. The cap is *rows served to
                    the client*, not rows scanned.
    """
    # `stream()` opens a server-side cursor; `yield_per` tells SQLAlchemy how
    # many rows to buffer per fetch. Without `yield_per` you can still iterate,
    # but the default buffering can be larger than you'd like.
    streamed = await session.stream(stmt.execution_options(yield_per=chunk_size))

    served = 0
    async for row in streamed.scalars():
        yield row
        served += 1
        if max_rows and served >= max_rows:
            # Closing the underlying cursor is handled when the session exits
            # via the FastAPI dependency. We just stop pulling.
            break
