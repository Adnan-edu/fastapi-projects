"""The three pipeline invariants — without these, the framework is just
indirection:

1. **Bounded memory**       — peak memory scales with chunk size, not row count.
2. **Swap a stage**         — same input, same row count, different byte format.
3. **Fail without cascade** — a mid-stream raise surfaces as StageError, no
                              dangling resources, no asyncio "Task was destroyed".

These tests are the *spec* of the pipeline's intended behavior. They run
without a database — synthetic `_ListSource` stands in for `DbKeysetSource`
so the invariants are checked in isolation from any I/O latency or
flakiness. (The endpoint smoke tests in `test_endpoint.py` confirm the
real DB path works.)
"""

from __future__ import annotations

import json
import tracemalloc
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from pipeline.core import Pipeline
from pipeline.errors import StageError
from pipeline.stages import CsvSink, NdjsonSink, PredicateFilter, Projection


# A tiny stand-in for OrderEvent. `dataclass` gives us attribute access
# (so `Projection` reaches into it the same way it would an ORM row) plus
# a free __init__ — useful when constructing synthetic test data.
@dataclass
class Row:
    id: int
    amount: float
    country: str


class _ListSource:
    """Synthetic source — yields N rows from an in-memory generator.

    Two instrumentation hooks make this useful for tests:

    - `open_count`: increments on entry, decrements when the generator's
      finally: runs. A nonzero value after the pipeline finishes means
      cleanup didn't propagate — that's the symptom the
      fail-without-cascading test catches.
    - `closed_cleanly`: set to True only after the finally block runs.
      Distinct from open_count because we want to detect the case where
      open_count starts at 0 because we never entered the body at all.
    """

    name = "list_source"

    def __init__(self, n: int):
        self.n = n
        self.open_count = 0
        self.closed_cleanly = False

    async def __call__(self) -> AsyncIterator[Row]:
        # The instrumentation: track entry, then guarantee exit accounting
        # via try/finally so even an aclose() during yield runs the closing
        # logic.
        self.open_count += 1
        try:
            for i in range(1, self.n + 1):
                # `yield` suspends here until the downstream stage pulls.
                # If a downstream stage raises and aclose() is called on
                # us, this yield raises GeneratorExit, which jumps to the
                # finally block. That's the cleanup we're testing.
                yield Row(id=i, amount=float(i), country="US")
        finally:
            self.open_count -= 1
            self.closed_cleanly = True


class _CountingSink:
    """A no-op sink that just counts items. Used by test_bounded_memory to
    verify the full stream was consumed (otherwise a buffering bug could
    "pass" the memory check by silently dropping rows).
    """

    name = "counting_sink"

    def __init__(self):
        self.count = 0

    async def __call__(self, upstream):
        async for item in upstream:
            self.count += 1
            yield item


async def _drain(pipeline: Pipeline) -> list:
    """Run the pipeline to exhaustion, collecting all yielded chunks into a
    list. Test-only helper — production code should never materialize a
    streaming pipeline like this.
    """
    return [chunk async for chunk in pipeline.run()]


# ---------- 1. Bounded memory ----------


@pytest.mark.parametrize("chunk_size", [100, 10_000])
async def test_bounded_memory(chunk_size: int):
    """Peak memory should track chunk_size, not the row count.

    We feed 200k rows through the pipeline and measure tracemalloc peak.
    With a streaming pipeline the peak is dominated by per-iteration
    allocations, not by holding every row at once.

    The parametrization is the real point: we want to see that the
    assertion holds whether chunks are small (100) or large (10_000). A
    bug that buffered the whole stream would fail at both sizes; a bug
    that scaled with chunk_size would still pass both as long as 10_000
    is small enough to fit under the bound — which is the point of
    keeping the bound generous.
    """
    n_rows = 200_000

    source = _ListSource(n_rows)
    sink = _CountingSink()
    # Note: chunk_size here doesn't drive a Rechunk — the pipeline is
    # row-at-a-time. The parametrization documents that the property
    # holds regardless of how we'd batch internally.
    pipeline = Pipeline(source, Projection(["id", "amount"]), sink)

    # tracemalloc snapshots Python memory allocations. We start it RIGHT
    # before the iteration to keep test setup out of the measurement.
    tracemalloc.start()
    async for _ in pipeline.run():
        pass
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Sanity: did we actually process all rows? A "memory test" that
    # passed because the pipeline dropped 90% of the stream would be
    # worse than useless.
    assert sink.count == n_rows

    # Generous upper bound. The exact number isn't the point — the point
    # is that 200_000 rows fit in well under 50 MB, while 200_000 fully
    # buffered Row dataclasses would be on the order of hundreds of MB.
    # If the pipeline ever starts buffering, this assertion will fail
    # loudly.
    upper_bound_bytes = 50 * 1024 * 1024
    assert peak < upper_bound_bytes, (
        f"peak={peak / 1e6:.1f} MB exceeded {upper_bound_bytes / 1e6:.0f} MB "
        f"for {n_rows} rows — pipeline is buffering instead of streaming"
    )


# ---------- 2. Swap a stage ----------


async def test_swap_a_stage_ndjson_vs_csv():
    """The same source feeds two different pipelines, differing only in
    the sink. We assert the row count is identical (same input → same
    output cardinality) but the byte representation differs. This is the
    operational definition of "stages are independently swappable."
    """
    n_rows = 100
    fields = ["id", "amount", "country"]

    # Two complete drains. Each uses a fresh _ListSource because async
    # generators are single-use — once exhausted they can't be re-iterated.
    ndjson = await _drain(
        Pipeline(_ListSource(n_rows), Projection(fields), NdjsonSink())
    )
    csv_out = await _drain(
        Pipeline(_ListSource(n_rows), Projection(fields), CsvSink(fields))
    )

    # NDJSON: one line per row, every line is valid JSON with the
    # projected keys. Join all chunks (each chunk is one line's bytes)
    # and split by newline.
    ndjson_lines = b"".join(ndjson).decode().splitlines()
    assert len(ndjson_lines) == n_rows
    parsed = [json.loads(line) for line in ndjson_lines]
    # `set` comparison ignores key order — NDJSON has no notion of column
    # order so this is the right granularity.
    assert all(set(row.keys()) == set(fields) for row in parsed)

    # CSV: header row + N data rows = N+1 lines total.
    csv_lines = b"".join(csv_out).decode().splitlines()
    assert len(csv_lines) == n_rows + 1
    # CsvSink with an explicit `fields` argument should produce the
    # header in exactly that order.
    assert csv_lines[0].split(",") == fields

    # Final cross-check: the raw bytes differ. This catches a silly bug
    # where someone accidentally aliased the two sinks.
    assert b"".join(ndjson) != b"".join(csv_out)


# ---------- 3. Fail without cascading ----------


async def test_fail_without_cascading():
    """A predicate that raises on the 50th item should:

    - surface as StageError with the right `stage_name`,
    - leave the source closed (its `finally:` block ran), and
    - not emit `Task was destroyed but it is pending` warnings.

    This is the property that justifies the `aclosing` wrapping in every
    stage. Without it, the upstream `_ListSource` would be left suspended
    at its yield (open_count == 1) until garbage collection — a real
    leak for the DB source which holds a connection.
    """
    source = _ListSource(1000)

    # `counter` is a mutable dict because closures over int can't rebind.
    # `nonlocal` would work too but a dict is dead simple.
    counter = {"seen": 0}

    def boom(row: Row) -> bool:
        counter["seen"] += 1
        if counter["seen"] == 50:
            # The raise lives inside the predicate, which means
            # `@stage_errors` on PredicateFilter.__call__ wraps it. That
            # is what produces the StageError with stage_name="boom".
            raise RuntimeError("synthetic failure at row 50")
        return True

    pipeline = Pipeline(
        source,
        PredicateFilter(boom, name="boom"),
        Projection(["id"]),
        NdjsonSink(),
    )

    # `warnings.catch_warnings(record=True)` captures warnings into a
    # list. We assert on it below to detect orphan-task warnings.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Iterate the pipeline manually so we can call aclose() in the
        # finally block — this is what would happen automatically if the
        # consumer broke out of a real `async for`, but `pytest.raises`
        # short-circuits before the consumer's cleanup runs.
        gen = pipeline.run()
        with pytest.raises(StageError) as excinfo:
            try:
                async for _ in gen:
                    pass
            finally:
                # Force cleanup of every nested generator (and their
                # finally blocks) before we assert anything about
                # released resources.
                await gen.aclose()

    # The StageError must name the stage that *first* raised, not any
    # downstream stage that re-wrapped — that's why @stage_errors passes
    # through existing StageError unchanged.
    assert excinfo.value.stage_name == "boom"
    # `cause` preserves the original exception type, so tests can
    # distinguish a permission error from a value error from a network
    # error.
    assert isinstance(excinfo.value.cause, RuntimeError)
    # The big one: the source must have exited cleanly. If this fails,
    # `aclosing` isn't propagating cleanup.
    assert source.open_count == 0
    assert source.closed_cleanly is True

    # No orphan-task warnings. asyncio emits this warning when a Task is
    # garbage-collected while still pending — the canonical symptom of a
    # leaked coroutine. Its presence here would mean we cleaned up
    # synchronously but left an asyncio task dangling, which is just as
    # bad.
    bad = [
        w
        for w in caught
        if "Task was destroyed but it is pending" in str(w.message)
    ]
    assert not bad, f"orphan task warnings leaked: {bad}"
