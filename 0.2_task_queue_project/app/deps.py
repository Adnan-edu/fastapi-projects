# =====================================================================
# app/deps.py - FastAPI dependency injection helpers
# =====================================================================
# PURPOSE
# -------
# Collects the small "Depends()-able" callables used by route handlers:
#   - `arq_pool`   : yields the shared ARQ Redis pool
#
# These are deliberately thin wrappers — the real implementations live
# in app/arq_utils.py. Keeping them here means routers import from one
# place ("from app.deps import ...") and we can swap implementations
# without touching every route.
#
# Note: the per-request AsyncSession dependency lives in app/database.py
# as `get_db` — routers import it directly from there.
# =====================================================================

# ArqRedis is the connection-pool object returned by arq.create_pool();
# it exposes `enqueue_job`, `close`, etc.
from arq.connections import ArqRedis

# Pull the actual implementation from its owning module.
from app.arq_utils import get_redis_pool


# Returns the singleton Redis pool used to enqueue ARQ jobs. The pool
# is created on first call (inside get_redis_pool) and reused on every
# subsequent request — opening a new pool per request would be wasteful.
async def arq_pool() -> ArqRedis:
    return await get_redis_pool()
