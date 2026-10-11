"""Error type + decorator used by every stage in the pipeline.

Two things live here, and they belong together:

1. `StageError` — a typed exception that names *which* stage failed and *why*.
   Every framework-level error visible to a caller (the HTTP handler, a test,
   another stage downstream) is a `StageError`. Plain `Exception` should not
   escape a stage boundary.

2. `stage_errors` — a decorator applied to every stage's `__call__`. It
   funnels arbitrary exceptions raised inside the stage body into
   `StageError(self.name, e)`, while letting existing `StageError`s pass
   through unchanged. Without it, each stage would need its own
   `try / except StageError: raise / except Exception as e: raise StageError(...)`
   boilerplate — five stages × the same pattern is exactly the kind of
   repetition a tiny decorator is built for.
"""

from collections.abc import AsyncIterator, Callable
from functools import wraps


class StageError(Exception):
    """A typed failure that carries the stage's name and the underlying cause.

    `stage_name` is what the HTTP handler reports back to the consumer in the
    trailing error NDJSON line ({"type":"error","stage":"db_keyset_source",...}),
    so the consumer can tell whether the failure was a DB problem, a bad
    predicate, a serializer issue, etc.

    `cause` keeps the original exception alive so tests can assert on its
    type — `assert isinstance(excinfo.value.cause, RuntimeError)` is what the
    fail-without-cascading test relies on.
    """

    def __init__(self, stage_name: str, cause: BaseException):
        super().__init__(f"stage '{stage_name}' failed: {cause!r}")
        self.stage_name = stage_name
        self.cause = cause


def stage_errors(fn: Callable[..., AsyncIterator]) -> Callable[..., AsyncIterator]:
    """Translate any non-StageError into StageError(self.name, e).

    Why a decorator instead of inheritance or a context manager?
    - Every stage's `__call__` is an async generator. Async generators can't
      cleanly be wrapped by a base-class method (you'd have to make every
      subclass implement a `_body` hook that the base then iterates).
    - A context manager wouldn't catch StopAsyncIteration / GeneratorExit
      semantics cleanly when the consumer aclose()s us mid-iteration.
    - A decorator wraps the generator's `__call__` symmetrically: same
      arguments in, same async-iterator out. The wrapper itself is an async
      generator, so `yield from`-style delegation works naturally.

    Why re-raise StageError unchanged?
    - When stage B's downstream stage C wraps in `StageError("C", ...)`, B's
      original `stage_name` would be lost. By passing through any existing
      StageError, the original failing stage's identity survives the entire
      chain.
    """

    @wraps(fn)
    async def wrapper(self, *args, **kwargs):
        try:
            # `fn(self, ...)` is itself an async generator. We iterate it
            # and re-yield each item, which gives the caller the same
            # streaming behavior as if they'd called the undecorated method.
            async for item in fn(self, *args, **kwargs):
                yield item
        except StageError:
            # Preserve the original stage's name on rethrow.
            raise
        except Exception as e:
            # Everything else gets named after the current stage.
            # `from e` keeps the original traceback chained for debugging.
            raise StageError(self.name, e) from e

    return wrapper
