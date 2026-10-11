"""fastapi-cache2 init (decorator path) + SCAN-based invalidation helpers.

Two caching styles are taught side-by-side:
1. Decorator (@cache) — used by legacy weather routes + /products/featured.
2. Manual cache-aside with redis.asyncio — used by product/cart/analytics routes
   (explicit GET/SETEX/DEL, visible in redis-cli, full TTL control).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from app.core import cache_keys as keys
from app.core.config import settings
from app.core.redis import close_redis, get_client


def city_key_builder(
    func: Any,
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
) -> str:
    city = kwargs.get("city", "") if kwargs else ""
    return f"{namespace}:{city.lower()}"


@asynccontextmanager
async def lifespan_with_redis(app: FastAPI) -> AsyncIterator[None]:
    """Production lifespan: real Redis only, fail fast with a clear error."""
    client = get_client()
    await client.ping()  # fail fast if Docker Redis is down
    FastAPICache.init(
        RedisBackend(client),  # type: ignore[arg-type]
        prefix=settings.cache_prefix,
        key_builder=city_key_builder,
        cache_status_header="X-Cache-Status",
    )
    # Seed autocomplete index (idempotent)
    try:
        from app.services import product_service

        for name in product_service.seed_names():
            await client.zadd(keys.AUTOCOMPLETE, {name.lower(): 0})
    except Exception:
        pass
    yield
    await close_redis()


@asynccontextmanager
async def lifespan_with_memory(app: FastAPI) -> AsyncIterator[None]:
    """Test-only lifespan (no Redis required)."""
    FastAPICache.init(
        InMemoryBackend(),
        prefix=settings.cache_prefix,
        key_builder=city_key_builder,
        cache_status_header="X-Cache-Status",
    )
    yield


async def scan_delete(client: aioredis.Redis, pattern: str, count: int = 200) -> int:
    """Delete by SCAN (never KEYS). Returns number of keys removed."""
    removed = 0
    async for key in client.scan_iter(match=pattern, count=count):
        try:
            removed += await client.unlink(key)  # type: ignore[arg-type]
        except Exception:
            try:
                removed += await client.delete(key)  # type: ignore[arg-type]
            except Exception:
                pass
    return removed


async def invalidate_product(pid: int | str) -> None:
    """Call on every product write: single key + list/search patterns + pub/sub event."""
    client = get_client()
    try:
        await client.delete(keys.product_key(pid))
    except Exception:
        pass
    try:
        await scan_delete(client, keys.PRODUCT_LIST_PATTERN)
        await scan_delete(client, keys.PRODUCT_SEARCH_PATTERN)
        await client.delete(keys.FEATURED)
    except Exception:
        pass
    try:
        await client.publish(keys.CHANNEL_PRODUCT_UPDATES, str(pid))
    except Exception:
        pass


# --- Legacy weather invalidation (kept for backwards compat) ---


async def clear_city_cache(city: str) -> bool:
    backend = FastAPICache.get_backend()
    prefix = FastAPICache.get_prefix()
    key = f"{prefix}:weather:{city.lower()}"
    try:
        await backend.clear(key=key)
        return True
    except Exception:
        return False


async def clear_all_cache() -> bool:
    backend = FastAPICache.get_backend()
    try:
        if isinstance(backend, InMemoryBackend):
            prefix = FastAPICache.get_prefix()
            try:
                await backend.clear(namespace=prefix)
            except TypeError:
                InMemoryBackend._store.clear()
            return True
        # Real Redis: SCAN-delete everything under our prefix (+ v1 product keys)
        client = get_client()
        prefix = FastAPICache.get_prefix()
        await scan_delete(client, f"{prefix}*")
        await scan_delete(client, f"{keys.V}*")
        return True
    except Exception:
        return False
