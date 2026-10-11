"""DbKeysetSource — keyset-paginated database source.

Why keyset pagination instead of LIMIT / OFFSET?
------------------------------------------------
OFFSET pagination at scale is a trap. To return rows 500 000–501 000, the DB
has to scan the first 500 000 rows and discard them. The cost grows linearly
with the offset. Keyset pagination (a.k.a. "seek pagination") replaces OFFSET
with a WHERE clause on the primary key:

    WHERE id > :last_id ORDER BY id LIMIT :chunk_size

Because `id` is indexed (it's the PK), this is an index seek, O(log n) +
the chunk size — flat per chunk no matter how deep into the table you go.

Why one short session per chunk instead of one long server-side cursor?
-----------------------------------------------------------------------
A server-side cursor (Postgres DECLARE … CURSOR) is appealing: it lets you
stream rows from the database without re-issuing the query. But it requires
the connection to stay open and inside a transaction for the lifetime of the
HTTP response. If the response takes 30 seconds, you've held a connection for
30 seconds. If 50 clients export at once, you've held 50 connections.

The short-session pattern trades a tiny per-chunk overhead (a few millis to
acquire a pooled connection and parse the same prepared statement again) for
two big wins:

1. **Connection lifetime is bounded by chunk size.** A chunk of 1000 rows
   completes in milliseconds; the connection goes back to the pool.
2. **Failure containment.** If a downstream stage raises mid-stream, we are
   guaranteed to be *between* chunks — there is no open session to leak.
   This is what makes the "fail-without-cascading" invariant true.
"""

from collections.abc import AsyncIterator, Sequence

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import OrderEvent
from pipeline.errors import stage_errors


class DbKeysetSource:
    # `name` is what shows up in StageError("db_keyset_source", ...) and in
    # the {"type":"error","stage":"db_keyset_source",...} NDJSON line the
    # HTTP handler emits. Keep it short and human-readable.
    name = "db_keyset_source"

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        chunk_size: int,
        after_id: int = 0,
        where_clauses: Sequence[ColumnElement] | None = None,
        max_rows: int = 0,
    ):
        """
        Parameters
        ----------
        sessionmaker
            The shared async_sessionmaker. We open one session per chunk
            using this factory; we don't hold a session across yields.
        chunk_size
            How many rows to pull per round-trip. Bigger = fewer round-trips
            but more memory per chunk; smaller = lower TTFB and lower memory
            ceiling. The bounded-memory invariant scales with this number.
        after_id
            Keyset cursor for resumption. `0` means start from the beginning;
            any other value means "give me rows with id > this".
        where_clauses
            Optional SQL filters pushed into the WHERE clause. Anything you
            can express in SQL should go here so non-matching rows never
            cross the DB/Python boundary. The HTTP handler uses this for the
            `status=…` query param.
        max_rows
            Optional hard cap on total rows emitted (`0` = unbounded). Used
            by the `limit=…` query param.
        """
        if chunk_size <= 0:
            # Fail-fast at construction time rather than mid-iteration. A
            # zero or negative chunk_size would cause an infinite loop below.
            raise ValueError("chunk_size must be positive")
        self.sessionmaker = sessionmaker
        self.chunk_size = chunk_size
        self.after_id = after_id
        # Materialize to a list so we don't accidentally re-iterate a
        # consumed generator if the caller passed one.
        self.where_clauses = list(where_clauses or ())
        self.max_rows = max_rows

    @stage_errors
    async def __call__(self) -> AsyncIterator[OrderEvent]:
        """Yield OrderEvent rows in id-ascending order.

        The control flow:
          1. Compute the next chunk's effective `limit`, respecting `max_rows`.
          2. Build a SELECT with the keyset condition and any extra filters.
          3. Open a short session, fetch the chunk, close the session.
          4. Yield each row, updating the in-memory cursor as we go.
          5. Stop when the DB returns a short page (= we've reached the end)
             or when `max_rows` is exhausted.
        """
        # Local copies so we can mutate them per-iteration without touching
        # `self` (keeps the source re-usable if someone calls __call__ twice).
        last_id = self.after_id
        emitted = 0

        while True:
            # ----- Step 1: figure out how many rows to ask for this chunk
            if self.max_rows:
                remaining = self.max_rows - emitted
                if remaining <= 0:
                    # Hit the user's hard cap. Done.
                    return
                # Never pull more than we still need — this is what lets
                # `limit=5` honestly return 5 rows even if chunk_size=1000.
                limit = min(self.chunk_size, remaining)
            else:
                # max_rows == 0 means "unbounded" — pull a full chunk each time.
                limit = self.chunk_size

            # ----- Step 2: build the SELECT
            # Note: `.where()` is chainable; each call ANDs another condition.
            stmt = (
                select(OrderEvent)
                .where(OrderEvent.id > last_id)
                .order_by(OrderEvent.id)
                .limit(limit)
            )
            for clause in self.where_clauses:
                stmt = stmt.where(clause)

            # ----- Step 3: open a short session, fetch, close
            # `async with self.sessionmaker()` is the SQLAlchemy idiom: it
            # opens a session, ensures `.close()` runs on exit even if we
            # raise. Crucially, we DRAIN the result into a Python list
            # *inside* the `with` block — `.scalars().all()` materializes
            # the chunk. Once we exit the block, the connection is back in
            # the pool. We then yield from the local list, decoupled from
            # the DB.
            async with self.sessionmaker() as session:
                rows = (await session.execute(stmt)).scalars().all()

            # ----- Step 4: handle the chunk
            if not rows:
                # Empty page = no more matching data. Done.
                return

            for row in rows:
                # `yield` suspends this coroutine until the downstream stage
                # asks for the next item. While suspended, we hold no DB
                # connection — that's the safety property.
                yield row
                emitted += 1

            # Advance the keyset cursor for the next iteration.
            last_id = rows[-1].id

            # ----- Step 5: short-page early exit
            # If the DB returned fewer rows than we asked for, we've reached
            # the tail of the data; no point in issuing another round-trip
            # just to get an empty result.
            if len(rows) < limit:
                return
