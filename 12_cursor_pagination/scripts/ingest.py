"""Bulk-ingest `order_events_1m.csv` into PostgreSQL.

Design choices
--------------
* **asyncpg COPY** (`copy_records_to_table`) is the fastest practical path to
  load millions of rows from Python. It bypasses the per-row INSERT roundtrip
  and uses PostgreSQL's binary COPY protocol under the hood.
* **Streaming + chunking** via `csv.reader` keeps memory bounded — we never
  hold the whole CSV in RAM.
* **Resumability**: the script reads `MAX(id)` from the target table at
  startup and skips any CSV row with `id <= max_id`. So a crashed/aborted
  ingest can simply be rerun; rows already loaded are not re-attempted.
* **Schema bootstrap**: if `order_events` does not exist, we create it plus
  the composite `(created_at, id)` index that powers cursor pagination.

Usage
-----
    uv run python -m scripts.ingest                  # use defaults from .env
    uv run python -m scripts.ingest --batch-size 100000
    uv run python -m scripts.ingest --csv data/order_events_1m.csv

Environment
-----------
    ASYNCPG_URL    raw postgres URL (no '+asyncpg' suffix)
    CSV_PATH       defaults to data/order_events_1m.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ingest")


COLUMNS = (
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


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS order_events (
    id              BIGINT PRIMARY KEY,
    order_id        BIGINT       NOT NULL,
    customer_id     BIGINT       NOT NULL,
    event_type      TEXT         NOT NULL,
    status          TEXT         NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    currency        TEXT         NOT NULL,
    country         TEXT         NOT NULL,
    payment_method  TEXT         NOT NULL,
    product_sku     TEXT         NOT NULL,
    quantity        INTEGER      NOT NULL,
    created_at      TIMESTAMP    NOT NULL,
    metadata        TEXT
);

CREATE INDEX IF NOT EXISTS ix_order_events_created_at_id
    ON order_events (created_at, id);
CREATE INDEX IF NOT EXISTS ix_order_events_customer_id
    ON order_events (customer_id);
CREATE INDEX IF NOT EXISTS ix_order_events_status
    ON order_events (status);
"""


def parse_row(row: list[str]) -> tuple:
    return (
        int(row[0]),
        int(row[1]),
        int(row[2]),
        row[3],
        row[4],
        Decimal(row[5]),
        row[6],
        row[7],
        row[8],
        row[9],
        int(row[10]),
        datetime.fromisoformat(row[11]),
        row[12] or None,
    )


def iter_csv(path: Path, skip_id_le: int) -> Iterator[tuple]:
    """Yield parsed rows from `path`, skipping any row whose id <= skip_id_le."""
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise SystemExit(
                f"Unexpected CSV header. Got {header!r}, expected {COLUMNS!r}."
            )
        for row in reader:
            if skip_id_le and int(row[0]) <= skip_id_le:
                continue
            yield parse_row(row)


def chunked(it: Iterator[tuple], size: int) -> Iterator[list[tuple]]:
    buf: list[tuple] = []
    for row in it:
        buf.append(row)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


async def ingest(csv_path: Path, dsn: str, batch_size: int) -> None:
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    log.info("Connecting to %s", _redact(dsn))
    conn: asyncpg.Connection = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(SCHEMA_SQL)
        max_id = int(await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM order_events") or 0)
        if max_id:
            log.info("Resuming: skipping rows with id <= %s", f"{max_id:,}")
        else:
            log.info("Empty table — starting fresh ingest")

        rows_iter = iter_csv(csv_path, skip_id_le=max_id)
        total = 0
        start = time.perf_counter()
        for batch in chunked(rows_iter, batch_size):
            # COPY is wrapped in an implicit transaction per call.
            await conn.copy_records_to_table(
                "order_events",
                records=batch,
                columns=COLUMNS,
            )
            total += len(batch)
            elapsed = time.perf_counter() - start
            rate = total / elapsed if elapsed else 0.0
            log.info(
                "Inserted batch=%s total=%s rate=%.0f rows/s",
                f"{len(batch):,}",
                f"{total:,}",
                rate,
            )

        # ANALYZE so the planner picks the composite index for cursor queries.
        log.info("Running ANALYZE order_events ...")
        await conn.execute("ANALYZE order_events")
        log.info("Done. Inserted %s rows in %.1fs", f"{total:,}", time.perf_counter() - start)
    finally:
        await conn.close()


def _redact(dsn: str) -> str:
    # postgresql://user:pass@host:port/db -> postgresql://user:***@host:port/db
    if "@" not in dsn or "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return dsn


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest order_events CSV into PostgreSQL")
    parser.add_argument(
        "--csv",
        default=os.getenv("CSV_PATH", "data/order_events_1m.csv"),
        help="Path to the CSV file.",
    )
    parser.add_argument(
        "--dsn",
        default=os.getenv("ASYNCPG_URL"),
        help="Raw asyncpg DSN (postgresql://user:pass@host:port/db).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("INGEST_BATCH_SIZE", "50000")),
        help="Rows per COPY batch.",
    )
    args = parser.parse_args()

    if not args.dsn:
        print("ERROR: --dsn or ASYNCPG_URL must be set.", file=sys.stderr)
        sys.exit(2)

    asyncio.run(ingest(Path(args.csv), args.dsn, args.batch_size))


if __name__ == "__main__":
    main()
