"""Shared redis.asyncio clients, cached per running event loop.

Why per-loop? `redis.asyncio` connections bind their transports to the loop
that created them. In production (uvicorn) there is a single loop, so a single
client is used. But Starlette's TestClient spins a fresh portal loop per
request — reusing one global client then fails with
`RuntimeError: Event loop is closed`. Caching one pool+client per loop keeps
both production (1 client) and tests (N loops) correct.

Production notes:
- One pool per process-loop, created at startup, closed at shutdown.
- socket_timeout prevents a slow Redis from hanging the API.
- health endpoints use PING; reads fail-open, rate-limit/idempotency fail-closed
  (see route code for policy).
"""

from __future__ import annotations

import asyncio

from fastapi import Depends
from redis import asyncio as aioredis

from app.core.config import settings

_pools: dict[int, aioredis.ConnectionPool] = {}
_clients: dict[int, aioredis.Redis] = {}


def _loop_key() -> int:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0  # no running loop (e.g. import time) — caller must be in async ctx


def get_pool() -> aioredis.ConnectionPool:
    key = _loop_key()
    pool = _pools.get(key)
    if pool is None:
        pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_pool_size,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_timeout,
            decode_responses=True,
        )
        _pools[key] = pool
    return pool


def get_client() -> aioredis.Redis:
    key = _loop_key()
    client = _clients.get(key)
    if client is None:
        client = aioredis.Redis(connection_pool=get_pool())
        _clients[key] = client
    return client


async def ping_redis() -> bool:
    try:
        return await get_client().ping() is True
    except Exception:
        return False


async def redis_info(section: str | None = None) -> dict:
    client = get_client()
    try:
        return await client.info(section)  # type: ignore[return-value]
    except Exception as exc:
        return {"error": str(exc)}


async def close_redis() -> None:
    for client in list(_clients.values()):
        try:
            await client.aclose(close_connection_pool=False)
        except Exception:
            pass
    _clients.clear()
    for pool in list(_pools.values()):
        try:
            await pool.aclose()
        except Exception:
            pass
    _pools.clear()


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — use in routes needing raw Redis."""
    return get_client()


# Backwards-compat alias for Depends(get_redis_client)
async def get_redis_client() -> aioredis.Redis:
    return get_client()


RedisDep = Depends(get_redis)
