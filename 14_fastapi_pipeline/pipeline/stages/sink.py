"""Sinks — terminal stages that serialize items to bytes.

A Sink is the rightmost stage in a pipeline. Its job is the
"object → bytes" boundary: turn each upstream item into a chunk of bytes
that can be written to a `StreamingResponse`, a file, or a network socket.

Sinks should be dumb. They:
- DO NOT batch across items beyond what their format requires for a single
  line/row.
- DO NOT hold open resources between yields (each item produces some bytes;
  those bytes are flushed immediately by the downstream consumer).
- DO use streaming-friendly serializers: `json.dumps` per line (NDJSON),
  `csv.writer` per row (CSV). Never `json.dumps(list_of_all_items)` — that
  would buffer the entire stream in memory and defeat the whole point.
"""

import csv
import io
import json
from collections.abc import AsyncIterator, Iterable
from contextlib import aclosing

from pipeline.errors import stage_errors


class NdjsonSink:
    """Emit one JSON object per line (newline-delimited JSON, a.k.a. NDJSON).

    NDJSON is the right serialization for streaming because:
    - The consumer can parse each line independently — no need to wait for
      the closing `]` of a JSON array.
    - Errors mid-stream are recoverable: a malformed line can be skipped
      without poisoning the rest of the document.
    - Compression and grep work line-by-line as expected.

    `default=str` is a small but important detail: many of our values are
    Decimals and datetimes, neither of which `json.dumps` knows how to
    serialize by default. `str()` is the universal fallback — Decimal
    becomes its string form, datetime becomes ISO-8601-ish text. The
    downstream consumer (typically jq, pandas, or a JS app) handles those
    types fine.
    """

    name = "ndjson_sink"

    @stage_errors
    async def __call__(self, upstream: AsyncIterator) -> AsyncIterator[bytes]:
        async with aclosing(upstream):
            async for item in upstream:
                # Newline-terminated — every line is a complete JSON value.
                # `default=str` handles non-JSON-native types (Decimal,
                # datetime, UUID, …) without per-field special-casing.
                yield (json.dumps(item, default=str) + "\n").encode("utf-8")


class CsvSink:
    """Emit CSV bytes. Assumes upstream items are dicts.

    Header behavior
    ---------------
    - If `fields` is given at construction time, the header row is the
      provided list and column order is locked regardless of dict iteration
      order. This is the recommended path for predictable output.
    - If `fields` is None, the header is taken from the first item's keys.
      That's convenient for ad-hoc usage but means the column order depends
      on whatever Projection (or upstream) put in the dict — fine for
      humans, not great for downstream tooling that pins columns by index.

    Why csv.writer instead of f-string interpolation?
    -------------------------------------------------
    Because RFC 4180 quoting is subtle: commas inside fields, double quotes
    inside fields, newlines inside fields, leading/trailing whitespace. The
    standard library's csv module gets all of those right. Hand-rolling it
    is a classic source of "works in dev, breaks in prod when a customer's
    name has a comma" bugs.
    """

    name = "csv_sink"

    def __init__(self, fields: Iterable[str] | None = None):
        # tuple() to lock ordering; `None` is preserved so __call__ knows to
        # infer from the first item.
        self.fields = tuple(fields) if fields else None

    @stage_errors
    async def __call__(self, upstream: AsyncIterator[dict]) -> AsyncIterator[bytes]:
        header_written = False
        fields = self.fields
        async with aclosing(upstream):
            async for item in upstream:
                if not header_written:
                    # Lazy header: only resolve `fields` once we see the
                    # first item. This makes CsvSink work with empty
                    # streams too — no items → no header → zero bytes out.
                    if fields is None:
                        fields = tuple(item.keys())
                    yield _csv_row(fields)
                    header_written = True
                # `str(... or "")` would coerce None to the literal string
                # "None". `item.get(f, "")` returns "" for missing keys,
                # which is the right CSV behavior.
                yield _csv_row(str(item.get(f, "")) for f in fields)


def _csv_row(values: Iterable[str]) -> bytes:
    """Serialize one CSV row to bytes, handling quoting per RFC 4180.

    We allocate a fresh StringIO per row deliberately. Reusing one across
    rows would tangle with csv.writer's internal state and require manual
    truncation between calls — the per-row allocation is cheap (a few
    bytes), and the simplicity is worth it.
    """
    buf = io.StringIO()
    # `csv.writer.writerow` handles quoting, escaping, and line terminator.
    # `list(values)` materializes the generator — `csv.writer` reads the
    # sequence twice in some edge cases (column count check).
    csv.writer(buf).writerow(list(values))
    return buf.getvalue().encode("utf-8")
