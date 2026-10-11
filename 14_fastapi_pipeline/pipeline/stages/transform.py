"""Per-item transformation stages: Projection and Enrich.

These two cover the most common "shape the data" needs:

- **Projection**: pick a subset of fields, drop the rest. Output is always a
  dict, so downstream sinks (NDJSON, CSV) have a uniform input shape.

- **Enrich**: keep everything, add computed fields. Useful for joining in
  static lookups (`country_name = COUNTRIES[row.country]`), deriving values
  (`tax = amount * 0.2`), or attaching metadata from a side cache.

Both stages return dicts. We use dicts (not Pydantic models or dataclasses)
because the items flowing through the pipeline are heterogeneous: a Source
might yield ORM objects, an Enrich might add string keys, a downstream stage
might want to drop or rename fields. A dict is the lowest-common-denominator
shape that works with any sink.
"""

from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import aclosing

from pipeline.errors import stage_errors


class Projection:
    """Keep only the named fields. Emit each item as a dict.

    `fields` is materialized into a tuple at construction so it's immutable
    and ordered — that matters because CsvSink uses the dict's key order to
    determine column order (if no explicit field list is given to CsvSink).
    """

    name = "projection"

    def __init__(self, fields: Iterable[str]):
        # tuple() so we don't accidentally consume a generator passed in by
        # the caller, and so re-iteration is cheap.
        self.fields = tuple(fields)

    @stage_errors
    async def __call__(self, upstream: AsyncIterator) -> AsyncIterator[dict]:
        async with aclosing(upstream):
            async for item in upstream:
                # `_get` handles both ORM objects (attribute access) and
                # dicts (key lookup). This is why Projection can come
                # second in a chain that started with a DbKeysetSource (ORM
                # rows) OR be chained after an Enrich (dicts).
                yield {f: _get(item, f) for f in self.fields}


class Enrich:
    """Merge the result of `fn(item)` into each item.

    The output is always a dict. If `item` is already a dict, we splat its
    keys directly. If it's an ORM object (or anything else), we wrap it
    under `_` to keep the original accessible while still allowing the
    enrichment dict to merge cleanly.

    Why does the output of fn() take precedence on key collisions?
    The dict-unpacking order `{**base, **self.fn(item)}` means later wins.
    Enrich is meant to *override* or *add* keys; if you want the original
    to win, do the merge yourself in `fn`.
    """

    name = "enrich"

    def __init__(self, fn: Callable[[object], dict]):
        self.fn = fn

    @stage_errors
    async def __call__(self, upstream: AsyncIterator) -> AsyncIterator[dict]:
        async with aclosing(upstream):
            async for item in upstream:
                # If item is already a dict, merge into it; otherwise stash
                # the original under "_" so downstream stages can still
                # reach it if they need to.
                base = item if isinstance(item, dict) else {"_": item}
                yield {**base, **self.fn(item)}


def _get(item: object, field: str):
    """Dict-or-attribute getter. Mirrors `getattr(obj, field, None)` for
    attribute-style objects and `dict.get(field)` for mappings.

    Returns None for missing keys/attributes rather than raising — Projection
    is happy to project nonexistent fields as null, which is a more useful
    default for streaming exports than crashing the response mid-flight.
    """
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)
