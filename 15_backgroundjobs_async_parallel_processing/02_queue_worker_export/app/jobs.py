"""The export job that runs *inside the Arq worker process* — not in the
API process.

The job is split into three pieces so each can be unit-tested without a
Postgres connection:

* :func:`build_export_sql` — pure SQL/arg builder (asyncpg positional
  placeholders, ``ORDER BY created_at, id`` to lean on the
  ``ix_order_events_created_at_id`` index).
* :func:`write_csv` — writes a CSV (header + rows) from any iterator of
  row-tuples. Pure I/O.
* :func:`run_export` — the Arq entrypoint. Connects to Postgres,
  streams rows through a server-side cursor (bounded memory), and hands
  them to :func:`write_csv`.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Iterable

# Whitelisted filter columns. Order matters: the positional placeholders
# in the generated SQL track this order.
FILTER_COLUMNS: tuple[str, ...] = ("status", "country", "customer_id")

# Columns selected on every export — also written as the CSV header.
COLUMNS: tuple[str, ...] = (
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

# How many rows asyncpg's cursor prefetches per network round-trip.
CHUNK = 10_000

EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "exports"))
DSN = os.environ.get(
    "ASYNCPG_DSN",
    "postgresql://cursor:cursor@localhost:5432/cursor_pagination",
)


def build_export_sql(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build the ``SELECT`` and the asyncpg argument list.

    Only keys in :data:`FILTER_COLUMNS` are honoured — everything else is
    silently dropped, so the request body can't reach SQL injection.
    """

    where: list[str] = []
    args: list[Any] = []
    for col in FILTER_COLUMNS:
        value = filters.get(col)
        if value is None:
            continue
        args.append(value)
        where.append(f"{col} = ${len(args)}")

    sql = f"SELECT {', '.join(COLUMNS)} FROM order_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at, id"
    return sql, args


def write_csv(
    rows: Iterable[tuple],
    path: Path,
    columns: Iterable[str] = COLUMNS,
) -> int:
    """Write ``rows`` to ``path`` as CSV. Returns the row count."""

    written = 0
    with Path(path).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(columns))
        for row in rows:
            # asyncpg returns ``Record`` (tuple-like); csv handles None
            # as an empty cell rather than the string "None".
            w.writerow(["" if v is None else v for v in row])
            written += 1
    return written


async def run_export(ctx, job_id: str, filters: dict) -> dict:
    """Arq entrypoint. ``ctx`` is the Arq job context."""

    # Lazy import — asyncpg is only needed inside the worker process.
    import asyncpg

    sql, args = build_export_sql(filters)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORT_DIR / f"{job_id}.csv"

    conn = await asyncpg.connect(DSN)
    try:
        # Server-side cursor — does NOT pull the whole result set into
        # memory.  Wrapping in a transaction is required for cursors.
        async with conn.transaction():
            cur = conn.cursor(sql, *args, prefetch=CHUNK)

            async def _row_iter():
                async for record in cur:
                    yield tuple(record)

            # ``write_csv`` is sync, but ``_row_iter`` is async — bridge
            # by materialising rows in chunks. We hand the writer an
            # async generator wrapped as a regular generator via batch
            # collection to keep memory bounded by ``CHUNK``.
            written = await _stream_to_csv(_row_iter(), out)
    finally:
        await conn.close()

    return {"job_id": job_id, "rows": written, "path": str(out)}


async def _stream_to_csv(async_rows, path: Path) -> int:
    """Internal: drive an async row iterator through :func:`write_csv`
    using a tiny in-memory buffer of size ``CHUNK``."""

    buf: list[tuple] = []
    written = 0
    with Path(path).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(COLUMNS))
        async for row in async_rows:
            buf.append(tuple("" if v is None else v for v in row))
            if len(buf) >= CHUNK:
                w.writerows(buf)
                written += len(buf)
                buf.clear()
        if buf:
            w.writerows(buf)
            written += len(buf)
    return written
