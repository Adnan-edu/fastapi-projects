"""Tests for the multiprocessing Parquet export job."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.parquet_export import (
    COLUMNS,
    plan_ranges,
    process_chunk,
    run_export_job,
)


def test_plan_ranges_partitions_id_space(dsn: str) -> None:
    """plan_ranges must cover [MIN(id), MAX(id)] without gaps and produce N ranges."""
    ranges = plan_ranges(4, dsn=dsn)
    assert len(ranges) == 4
    # Contiguous and non-overlapping
    for (a_lo, a_hi), (b_lo, b_hi) in zip(ranges, ranges[1:]):
        assert a_lo <= a_hi
        assert b_lo == a_hi + 1
    # First range starts at the min
    assert ranges[0][0] == 1
    # Last range ends at the max
    assert ranges[-1][1] == 1_000_000


def test_plan_ranges_rejects_zero_workers() -> None:
    with pytest.raises(ValueError):
        plan_ranges(0)


def test_process_chunk_writes_partitioned_parquet(tmp_out_root: Path) -> None:
    """A single worker writes country=.../event_type=.../*.parquet files."""
    result = process_chunk((1, 5_000))
    assert result["rows"] == 5_000
    files = list(tmp_out_root.rglob("*.parquet"))
    assert files, "expected at least one parquet file"
    # At least one partition path has both keys
    sample = files[0].as_posix()
    assert "country=" in sample
    assert "event_type=" in sample


def test_process_chunk_schema_matches_columns(tmp_out_root: Path) -> None:
    """Written Parquet files (minus partition columns) carry the expected schema."""
    process_chunk((1, 2_000))
    dataset = pq.ParquetDataset(str(tmp_out_root))
    schema_names = set(dataset.schema.names)
    expected = set(COLUMNS)
    # partition cols ARE present in the dataset schema (pyarrow re-attaches them)
    missing = expected - schema_names
    assert not missing, f"missing columns in dataset schema: {missing}"


def test_run_export_job_full_dataset(tmp_out_root: Path) -> None:
    """End-to-end: 4 workers, every row from the DB lands in the Parquet dataset."""
    results = run_export_job(num_workers=4)
    assert len(results) == 4
    assert sum(r["rows"] for r in results) == 1_000_000

    dataset = pq.ParquetDataset(str(tmp_out_root))
    total = sum(f.metadata.num_rows for f in [pq.ParquetFile(p) for p in dataset.files])
    assert total == 1_000_000


def test_api_endpoint_runs_job(tmp_out_root: Path) -> None:
    """The FastAPI launcher dispatches the job and returns a row total."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/export/parquet", params={"workers": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["workers"] == 2
    assert body["total_rows"] == 1_000_000
    assert len(body["chunks"]) == 2


def test_api_endpoint_rejects_invalid_workers() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/export/parquet", params={"workers": 0})
    assert resp.status_code == 200
    assert "error" in resp.json()
