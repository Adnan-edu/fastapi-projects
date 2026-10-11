# =====================================================================
# app/arq_utils.py - ARQ Redis pool singleton helpers
# =====================================================================
# PURPOSE
# -------
# ARQ talks to Redis through a connection pool (`ArqRedis`). Creating
# a pool is expensive (TCP handshake, auth, etc.), so we want exactly
# ONE pool per process and reuse it across every API request.
#
# This module exposes two functions:
#   - get_redis_pool()    -> returns the shared ArqRedis (creates on first call)
#   - close_redis_pool()  -> closes the pool cleanly on app shutdown
#
# The lifespan() handler in main.py calls get_redis_pool() at startup
# and close_redis_pool() on shutdown.
# =====================================================================

# `create_pool` is ARQ's factory function for ArqRedis pools.
from arq import create_pool

# Type imports: ArqRedis is the pool class; RedisSettings carries the
# host/port/auth used to build it.
from arq.connections import ArqRedis, RedisSettings

# Our app-wide settings object — we need its `redis_settings` property
# to know where Redis lives.
from app.config import settings


# Module-level mutable singleton. Initialised lazily on first request
# so importing this module doesn't touch Redis. The leading underscore
# signals "private — don't access directly from outside this module".
_redis_pool: ArqRedis | None = None


# Lazy accessor: returns the pool, creating it the first time it's
# requested. Subsequent calls reuse the same instance.
async def get_redis_pool() -> ArqRedis:
    # `global` is needed because we assign to the module-level variable
    # below. Without it, Python would treat _redis_pool as a local.
    global _redis_pool
    # If the pool has never been created (or was closed), build a new
    # one using the Redis settings derived from our config.
    if _redis_pool is None:
        _redis_pool = await create_pool(settings.redis_settings)
    return _redis_pool


# Counterpart to get_redis_pool: closes the pool and releases sockets.
# Called from the FastAPI lifespan shutdown phase (see main.py).
async def close_redis_pool():
    global _redis_pool
    # Guard against double-close. If startup never ran (e.g. failure
    # before lifespan completed) the pool may still be None.
    if _redis_pool is not None:
        # `close_connection_pool=True` ensures every pooled socket is
        # released, not just the wrapper object.
        await _redis_pool.close(close_connection_pool=True)
        # Reset to None so any later call to get_redis_pool() rebuilds
        # a fresh pool (useful in tests).
        _redis_pool = None
