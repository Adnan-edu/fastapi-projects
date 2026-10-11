"""Async database engine and session factory.

Two access patterns in one module
---------------------------------
This app has two distinct DB usage shapes that need slightly different
plumbing:

1. **Request handlers** (e.g. `/readyz`) want a single session injected by
   FastAPI's `Depends`. They use `get_session()` — a generator dependency
   that opens a session, hands it to the route, and closes it on response.

2. **The pipeline** opens its OWN session per chunk inside `DbKeysetSource`.
   It needs the *factory* (`async_sessionmaker`), not a single session
   instance, so it can call `sessionmaker()` repeatedly. That's what
   `get_sessionmaker()` returns.

Why module-level singletons?
----------------------------
The engine and sessionmaker are created once at app startup (in the
FastAPI lifespan) and disposed once at shutdown. They have to be reachable
from request handlers without being passed around explicitly, so they live
as module-level `_engine` / `_sessionmaker`. The leading underscore signals
"do not poke directly from outside this module — use the accessors."

`_engine` is `None` between shutdown and the next startup. The accessors
raise a clear error if called outside a lifespan, so a misconfigured test
fixture fails fast instead of mysteriously crashing on the first query.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

# Module-level singletons. They're set by `init_engine()` (called from the
# FastAPI lifespan startup) and cleared by `dispose_engine()` (called from
# the lifespan shutdown). Tests that need DB access must call init_engine()
# themselves — see tests/test_endpoint.py.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    """Build the engine + sessionmaker. Idempotent if called twice in the
    same process by accident (the second call will overwrite without
    disposing the first — that's a leak, but we never do it intentionally).
    """
    global _engine, _sessionmaker
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        # Bound the concurrent checkout count. Beyond `pool_size +
        # max_overflow`, new acquisitions block until a connection is
        # returned. For a streaming export server this is a soft cap on
        # concurrent in-flight pipelines.
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # `pool_pre_ping=True` runs a lightweight SELECT 1 before handing a
        # pooled connection to the caller. It catches stale connections
        # (DB restart, network blip) without surfacing the failure as a
        # query error. Tiny cost; large reliability win.
        pool_pre_ping=True,
        future=True,
    )
    # `expire_on_commit=False` means ORM objects loaded inside a session
    # keep their attribute values usable after commit. The default
    # (True) re-fetches on next attribute access, which is the wrong
    # behavior for a yield-then-close-session pattern — we read attrs
    # AFTER the session has closed.
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Tear down the engine on app shutdown.

    `engine.dispose()` closes all pooled connections cleanly. We then null
    the singletons so any post-shutdown call to `get_sessionmaker()` fails
    with a clear error instead of trying to use a disposed engine.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (not a session). Used by the pipeline so
    it can open one short session per chunk.
    """
    if _sessionmaker is None:
        # Raise instead of returning None — this almost always means the
        # test forgot to set up the lifespan, and a None-deref later would
        # give a confusing AttributeError.
        raise RuntimeError("Database engine not initialized. Did lifespan run?")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends() generator: yields one AsyncSession per request.

    `async with sessionmaker()` ensures the session is closed at function
    exit (after the route handler finishes), no matter how it exits — clean
    return, raise, or client disconnect.
    """
    async with get_sessionmaker()() as session:
        yield session
