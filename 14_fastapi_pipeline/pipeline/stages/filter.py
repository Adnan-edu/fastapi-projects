"""PredicateFilter — drop items that don't match a Python callable.

When to use it
--------------
This is the escape hatch for "I couldn't express this in SQL." For anything
the database can do, push it into `DbKeysetSource.where_clauses` — that way
non-matching rows never cross the DB/Python boundary and you save the
serialization + network cost.

PredicateFilter's job is the rest:
- predicates that call external services ("is this customer GDPR-deleted?")
- predicates over derived/computed values that aren't in the schema
- predicates a human added late and hasn't yet pushed down to SQL

The implementation is intentionally tiny — there's nothing to optimize here
beyond "call the function, decide whether to yield."
"""

from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from typing import TypeVar

from pipeline.errors import stage_errors

T = TypeVar("T")


class PredicateFilter:
    # Default name. Constructor lets the caller override it so two filters
    # in the same pipeline get distinguishable names in StageError messages.
    name = "predicate_filter"

    def __init__(self, predicate: Callable[[object], bool], *, name: str | None = None):
        """
        Parameters
        ----------
        predicate
            A callable that returns True to keep an item, False to drop it.
            It receives one item at a time, in upstream order.
        name
            Optional override for `self.name`. Useful when you have several
            filters in the same pipeline ("min_amount", "is_active", …) and
            want error messages to identify which one failed.
        """
        self.predicate = predicate
        if name:
            # Per-instance override of the class attribute. Other instances
            # still see the default.
            self.name = name

    @stage_errors
    async def __call__(self, upstream: AsyncIterator[T]) -> AsyncIterator[T]:
        """Yield items where `predicate(item)` is truthy.

        Why wrap `upstream` in `aclosing`?
        ----------------------------------
        If the predicate (or any downstream stage we yield to) raises, we
        need the upstream generator to also have its `finally:` blocks run.
        Python's async generator machinery doesn't propagate cleanup
        automatically — a paused `async for ... yield` upstream stays
        suspended until something explicitly aclose()s it.

        `async with aclosing(upstream)` registers a guaranteed `aclose()`
        call on the upstream when control leaves this `with` block, no
        matter the reason — normal completion, an exception bubbling out,
        or the consumer aclose()ing us. That call cascades layer by layer
        up to the Source, which is why the fail-without-cascading invariant
        holds end-to-end.
        """
        async with aclosing(upstream):
            async for item in upstream:
                # Note: a raise inside `predicate(item)` is caught by the
                # `@stage_errors` decorator and re-raised as
                # StageError(self.name, e). That's how the
                # fail-without-cascading test arms the failure.
                if self.predicate(item):
                    yield item
