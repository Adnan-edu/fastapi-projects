"""The idempotent export job — runs inside the Arq worker process.

Three idempotency mechanisms are layered:
1. Deterministic output filename from :func:`idempotency_key` — same
   filters always map to the same path.
2. Existence check at job entry — a previous successful run short-
   circuits this one.
3. Temp file (``.partial``) + atomic ``rename`` — a crash mid-write
   leaves no half-written file that could fool the existence check.

Together they make ``max_tries=5`` in the worker settings safe: every
retry is either a cache hit or a fresh start from an empty slate.
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Any

from app.ids import idempotency_key
from app.log_setup import log
from app.metrics import JOBS_COMPLETED, JOBS_STARTED, JOB_DURATION

EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "exports"))
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DSN = os.environ.get(
    "ASYNCPG_DSN",
    "postgresql://cursor:cursor@localhost:5432/cursor_pagination",
)

# Whitelisted filter columns — anything else in the request body is
# silently dropped before reaching SQL. This is also our injection guard.
FILTER_COLUMNS: tuple[str, ...] = ("status", "country", "customer_id")

# Columns selected on every export, also the CSV header.
COLUMNS: tuple[str, ...] = (
    "id", "order_id", "customer_id", "event_type", "status",
    "amount", "currency", "country", "payment_method", "product_sku",
    "quantity", "created_at", "metadata",
)

# Rows the asyncpg cursor prefetches per round-trip.
CHUNK = 10_000


def build_export_sql(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build the parametrised SELECT and the asyncpg positional args.

    Pure: no I/O, easy to unit-test. Only :data:`FILTER_COLUMNS` are
    honoured.
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


async def run_export(ctx, filters: dict) -> dict:
    """Arq entrypoint. ``ctx`` is the Arq job context (unused here)."""

    # Filter the body down to whitelisted keys so the idempotency key
    # doesn't change when callers stuff extra junk into the request.
    clean = {k: filters.get(k) for k in FILTER_COLUMNS if filters.get(k) is not None}

    key = idempotency_key(clean)
    out = EXPORT_DIR / f"{key}.csv"
    status_label = clean.get("status") or "any"
    JOBS_STARTED.labels(status_filter=status_label).inc()
    start = time.perf_counter()

    # --- Guard 2: existence check ---------------------------------
    if out.exists():
        log.info("export.skip_existing", key=key, path=str(out))
        JOBS_COMPLETED.labels(outcome="skipped").inc()
        JOB_DURATION.observe(time.perf_counter() - start)
        return {"key": key, "path": str(out), "skipped": True}

    # --- Guard 3: temp file + atomic rename -----------------------
    tmp = out.with_suffix(".csv.partial")

    sql, args = build_export_sql(clean)
    rows_written = 0

    import asyncpg  # local import — only needed in the worker process

    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            with tmp.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                async for row in conn.cursor(sql, *args, prefetch=CHUNK):
                    # asyncpg returns Records; csv treats None as "".
                    w.writerow(["" if v is None else v for v in row])
                    rows_written += 1
        # Atomic on POSIX: retries can never observe a half-written file.
        tmp.rename(out)
    except Exception as exc:  # noqa: BLE001 — we log and re-raise
        log.exception("export.failed", key=key, error=str(exc))
        JOBS_COMPLETED.labels(outcome="failed").inc()
        if tmp.exists():
            tmp.unlink()
        raise
    finally:
        await conn.close()
        JOB_DURATION.observe(time.perf_counter() - start)

    log.info("export.done", key=key, rows=rows_written, path=str(out))
    JOBS_COMPLETED.labels(outcome="ok").inc()
    return {"key": key, "path": str(out), "rows": rows_written}
