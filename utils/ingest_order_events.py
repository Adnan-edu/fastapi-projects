"""Reusable CSV-to-PostgreSQL loader for the order_events dataset.

Usage:
    ASYNCPG_URL=postgresql://user:pass@localhost:5432/db \
    python ingest_order_events.py --csv data/order_events_1m.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import time
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg


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


SCHEMA_SQL = Path(__file__).with_name("order_events_schema.sql").read_text()


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
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise SystemExit(f"Unexpected CSV header: {header!r}")
        for row in reader:
            if skip_id_le and int(row[0]) <= skip_id_le:
                continue
            yield parse_row(row)


def chunked(rows: Iterator[tuple], size: int) -> Iterator[list[tuple]]:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def ingest(csv_path: Path, dsn: str, batch_size: int) -> None:
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(SCHEMA_SQL)
        max_id = int(await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM order_events") or 0)
        total = 0
        start = time.perf_counter()

        for batch in chunked(iter_csv(csv_path, skip_id_le=max_id), batch_size):
            await conn.copy_records_to_table("order_events", records=batch, columns=COLUMNS)
            total += len(batch)
            elapsed = time.perf_counter() - start
            rate = total / elapsed if elapsed else 0.0
            print(f"inserted={total:,} batch={len(batch):,} rate={rate:.0f}/s")

        await conn.execute("ANALYZE order_events")
        print(f"done inserted={total:,} elapsed={time.perf_counter() - start:.1f}s")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=os.getenv("CSV_PATH", "data/order_events_1m.csv"))
    parser.add_argument("--dsn", default=os.getenv("ASYNCPG_URL"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("INGEST_BATCH_SIZE", "50000")))
    args = parser.parse_args()

    if not args.dsn:
        raise SystemExit("Set --dsn or ASYNCPG_URL.")

    asyncio.run(ingest(Path(args.csv), args.dsn, args.batch_size))


if __name__ == "__main__":
    main()
