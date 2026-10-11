"""Multiprocessing-based partitioned Parquet export of `order_events`.

Parent process: plans roughly-equal id ranges, dispatches them to a Pool.
Each worker process: opens its own sync psycopg connection, reads its slice,
converts to a PyArrow table and writes a partitioned Parquet dataset.
"""

from __future__ import annotations

import os
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq


DSN = os.environ.get(
    "PG_DSN",
    "postgresql://cursor:cursor@localhost:5432/cursor_pagination",
)

OUT_ROOT = Path(os.environ.get("PARQUET_OUT_ROOT", "data/export"))

COLUMNS = [
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
]


def plan_ranges(num_workers: int, dsn: str = DSN) -> list[tuple[int, int]]:
    """Split the id space into roughly equal contiguous ranges."""
    if num_workers <= 0:
        raise ValueError("num_workers must be >= 1")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(id), MAX(id) FROM order_events")
        row = cur.fetchone()
    if not row or row[0] is None:
        return []
    lo, hi = int(row[0]), int(row[1])
    step = (hi - lo + 1) // num_workers + 1
    return [(s, min(s + step - 1, hi)) for s in range(lo, hi + 1, step)]


def process_chunk(rng: tuple[int, int]) -> dict:
    """Worker entry point. Reads one id range and writes partitioned Parquet."""
    lo, hi = rng
    out_root = Path(os.environ.get("PARQUET_OUT_ROOT", str(OUT_ROOT)))
    out_root.mkdir(parents=True, exist_ok=True)
    dsn = os.environ.get("PG_DSN", DSN)

    sql = f"""
        SELECT {", ".join(COLUMNS)}
        FROM order_events
        WHERE id BETWEEN %s AND %s
    """
    t0 = time.perf_counter()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, (lo, hi))
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return {"range": rng, "rows": 0, "seconds": round(time.perf_counter() - t0, 3)}

    df["amount"] = df["amount"].astype("float64")

    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(out_root),
        partition_cols=["country", "event_type"],
        compression="zstd",
        existing_data_behavior="overwrite_or_ignore",
    )
    return {
        "range": rng,
        "rows": len(df),
        "seconds": round(time.perf_counter() - t0, 3),
    }


def run_export_job(num_workers: int = 4, dsn: str | None = None) -> list[dict]:
    """Plan ranges and fan out to a Pool of worker processes."""
    if dsn:
        os.environ["PG_DSN"] = dsn
    ranges = plan_ranges(num_workers, dsn or DSN)
    if not ranges:
        return []
    with Pool(processes=num_workers) as pool:
        return pool.map(process_chunk, ranges)
