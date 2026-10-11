"""Rechunk — regroup a one-at-a-time stream into bounded list[T] batches.

When to use it
--------------
Some downstream consumers are most efficient in batches, not in singletons:
- Bulk-inserting into another table (`session.execute(insert(T), batch_rows)`)
- Posting to an HTTP API that accepts arrays
- Writing to a columnar file format where per-row overhead dominates

The Source naturally emits one row at a time. Rechunk is the adapter that
bridges that to a batch-oriented consumer without breaking the bounded-memory
invariant.

The invariant
-------------
At most `size` items are held in memory at any moment. The current `batch`
list grows from 0 to `size`, is yielded (handing ownership to the consumer),
and is then replaced by a fresh empty list. A partial batch at end-of-stream
is also yielded — losing the tail would be silent data corruption.
"""

from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import TypeVar

from pipeline.errors import stage_errors

T = TypeVar("T")


class Rechunk:
    name = "rechunk"

    def __init__(self, size: int):
        if size <= 0:
            # A non-positive batch size is nonsensical — fail fast at
            # construction rather than producing an infinite empty stream.
            raise ValueError("Rechunk size must be positive")
        self.size = size

    @stage_errors
    async def __call__(self, upstream: AsyncIterator[T]) -> AsyncIterator[list[T]]:
        """Yield successive `list[T]` batches of at most `self.size` items.

        Note the structure: `batch = []` is created *once* and reused, but
        we replace it with a fresh list after each yield. This matters
        because once we yield a batch, the consumer owns that list — if we
        kept appending to the same object we'd be mutating something the
        consumer might still be reading.
        """
        batch: list[T] = []
        async with aclosing(upstream):
            async for item in upstream:
                batch.append(item)
                if len(batch) >= self.size:
                    yield batch
                    # Fresh list — see comment above.
                    batch = []
            # End-of-stream: flush whatever's left in the partial batch.
            # The `if batch` check avoids emitting a spurious empty list
            # when the total count is a clean multiple of `size`.
            if batch:
                yield batch
