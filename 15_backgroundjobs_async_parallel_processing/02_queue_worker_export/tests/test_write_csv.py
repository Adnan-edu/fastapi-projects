"""Unit tests for ``app.jobs.write_csv``.

This is the side-effecting half of the export job, isolated so we can
test it without Postgres. We hand it an iterator of row-tuples and
verify the file on disk.
"""

from __future__ import annotations

import csv

from app.jobs import COLUMNS, write_csv


def test_writes_header_only_when_no_rows(tmp_path):
    out = tmp_path / "empty.csv"
    rows_written = write_csv(iter([]), out, COLUMNS)
    assert rows_written == 0
    contents = out.read_text().splitlines()
    assert contents == [",".join(COLUMNS)]


def test_writes_header_and_rows(tmp_path):
    out = tmp_path / "two.csv"
    rows = [
        (1, 10, 100, "purchase", "paid", "9.99", "USD", "US", "card", "SKU-A",
         1, "2026-01-01T00:00:00", "{}"),
        (2, 11, 100, "purchase", "paid", "19.50", "USD", "US", "card", "SKU-B",
         2, "2026-01-02T00:00:00", None),
    ]
    rows_written = write_csv(iter(rows), out, COLUMNS)
    assert rows_written == 2

    with out.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)
    assert header == list(COLUMNS)
    assert body[0][0] == "1"
    assert body[1][0] == "2"
    # None becomes empty cell, not the literal string "None"
    assert body[1][-1] == ""
