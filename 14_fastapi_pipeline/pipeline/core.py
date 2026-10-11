"""Pipeline primitives: Stage, Source, and the Pipeline composer.

Mental model
------------
A pipeline is a chain of async generators. The leftmost element (the Source)
produces items from somewhere external — a database, a file, an HTTP feed.
Every subsequent element (a Stage) consumes the previous one's output and
produces a new stream of items. The rightmost element is typically a Sink that
serializes items to bytes for an HTTP response or a file.

Why async generators?
- Backpressure is automatic. A stage only pulls from upstream when its
  downstream consumer pulls from it. There is no producer thread racing
  ahead, no in-memory queue to size, no risk of OOM from a slow consumer.
- Composition is trivial. Calling `stage(upstream)` returns an async iterator,
  which is exactly what the next stage expects as input. The shape is
  preserved through the whole chain.
- Cleanup is uniform. Every generator has an `aclose()` method that runs its
  `finally:` blocks. Propagating cleanup is therefore a matter of calling
  `aclose()` on the outermost generator (which is what `contextlib.aclosing`
  does), and Python's coroutine machinery does the rest.

Why Protocol instead of an abstract base class?
- A Protocol is structural. Any class with the right shape *is* a Stage,
  without needing to inherit. This is important because some stages are
  trivial enough (e.g. a one-line `Projection`) that requiring inheritance
  would feel ceremonial.
- The `runtime_checkable` form lets `isinstance(x, Stage)` work in tests if
  you ever need to assert on it. We don't rely on it in production code.
"""

from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Protocol, TypeVar, runtime_checkable

# Generic type vars. T_in is what a stage consumes; T_out is what it produces.
# Python's Protocol can be parameterized with these, but in practice we keep
# the runtime annotations loose (AsyncIterator without a type arg) because
# each stage knows its own shape and the chain isn't statically typed.
T_in = TypeVar("T_in")
T_out = TypeVar("T_out")


@runtime_checkable
class Stage(Protocol):
    """Consumes an async iterator and produces another.

    Contract every Stage must honor:

    1. Be an async generator. The `__call__` must `yield`, not `return`.
       This is what enables backpressure and gives us `aclose()` for free.

    2. Yield items one at a time. Never accumulate the entire input into a
       list — that breaks the bounded-memory invariant. `Rechunk` is the
       only exception, and even it caps its internal buffer at `size` items.

    3. Close owned resources in a `finally:` block. If the stage opens a file
       or holds a DB connection, it must release it whether the generator
       completes normally, is aclose()d by a downstream cancellation, or
       raises.
    """

    name: str

    def __call__(self, upstream: AsyncIterator) -> AsyncIterator: ...


@runtime_checkable
class Source(Protocol):
    """First element of a pipeline. Takes no upstream; produces items from
    somewhere external. Same shape rules as Stage otherwise.
    """

    name: str

    def __call__(self) -> AsyncIterator: ...


class Pipeline:
    """Composes a Source and N Stages into a single async-iterable stream.

    Usage:

        pipeline = Pipeline(
            DbKeysetSource(sessionmaker, chunk_size=1000),
            PredicateFilter(lambda r: r.amount > 100),
            Projection(["id", "amount"]),
            NdjsonSink(),
        )
        async for chunk in pipeline.run():
            ...

    Pipelines are cheap to construct — they hold references, they don't open
    anything. The Source is only invoked when `run()` starts iterating, so
    nothing leaks if a pipeline is built and then discarded.
    """

    def __init__(self, source: Source, *stages: Stage):
        self.source = source
        self.stages = stages

    async def run(self) -> AsyncIterator:
        """Yield items end-to-end.

        Composition step: we call `source()` to get the first iterator, then
        each stage in turn — `stage(stream)` returns a new iterator that
        consumes the previous one. After the loop, `stream` is the outermost
        generator (the one closest to the consumer).

        Why `async with aclosing(stream)`?
        - If the consumer breaks out of the `async for` (or raises), we need
          to call `aclose()` on the outermost generator so its `finally:`
          blocks run. Each stage's body wraps its own upstream in `aclosing`,
          so `aclose()` propagates layer-by-layer up to the Source. Without
          this, a paused upstream generator (e.g. DbKeysetSource between
          chunks) would only be cleaned up at garbage-collection time — too
          late, often on the wrong event loop, and a guaranteed warning of
          'Task was destroyed but it is pending' or 'Event loop is closed'.
        """
        stream = self.source()
        for stage in self.stages:
            stream = stage(stream)
        async with aclosing(stream):
            async for item in stream:
                yield item
