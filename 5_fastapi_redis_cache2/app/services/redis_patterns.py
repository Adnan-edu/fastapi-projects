"""Shared Redis pattern helpers: locks, rate-limit, idempotency, cart, analytics.

Each function maps 1:1 to a Redis data structure so learners can inspect with redis-cli.
"""

from __future__ import annotations

import json
import time

from redis import asyncio as aioredis

from app.core import cache_keys as keys
from app.core.config import settings


# --- Distributed lock (cache stampede guard): String SET NX PX ---
async def acquire_lock(client: aioredis.Redis, pid: int | str, token: str) -> bool:
    try:
        return await client.set(keys.lock_key(pid), token, nx=True, px=settings.lock_ttl_ms) is True  # type: ignore[return-value]
    except Exception:
        return False  # fail-open: don't block reads if Redis is down


async def release_lock(client: aioredis.Redis, pid: int | str, token: str) -> None:
    try:
        val = await client.get(keys.lock_key(pid))
        if val == token:
            await client.delete(keys.lock_key(pid))
    except Exception:
        pass


# --- Fixed-window rate limit: Counter INCR + EXPIRE ---
async def check_rate_limit(client: aioredis.Redis, scope: str) -> tuple[bool, int, int]:
    """Returns (allowed, remaining, retry_after_s). Fail-closed on Redis errors? No:
    fail-open for learning, but production auth endpoints should fail-closed."""
    window = int(time.time() // settings.rate_limit_window_s)
    k = keys.ratelimit_key(scope, window)
    try:
        count = await client.incr(k)
        if count == 1:
            await client.expire(k, settings.rate_limit_window_s)
        ttl = await client.ttl(k)
        allowed = count <= settings.rate_limit_max
        return allowed, max(0, settings.rate_limit_max - count), 0 if allowed else max(0, ttl)
    except Exception:
        return True, settings.rate_limit_max, 0  # fail-open


# --- Idempotency: String SET NX EX, replay stored response ---
async def idempotency_replay(client: aioredis.Redis, key: str) -> dict | None:
    try:
        raw = await client.get(keys.idempotency_key(key))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def idempotency_store(client: aioredis.Redis, key: str, payload: dict) -> None:
    try:
        await client.set(keys.idempotency_key(key), json.dumps(payload, default=str),
                         ex=settings.idempotency_ttl)
    except Exception:
        pass


# --- Analytics: Counter + Sorted Set + HyperLogLog ---
async def track_view(client: aioredis.Redis, pid: int, viewer: str = "anon") -> int:
    try:
        total = await client.incr(keys.views_key(pid))
        await client.zincrby(keys.LEADERBOARD_VIEWS, 1, str(pid))
        try:
            await client.pfadd(keys.visitors_key(pid), viewer)
        except Exception:
            pass
        return int(total)
    except Exception:
        return 0


async def top_viewed(client: aioredis.Redis, n: int = 5) -> list[tuple[str, float]]:
    try:
        return await client.zrevrange(keys.LEADERBOARD_VIEWS, 0, n - 1, withscores=True)  # type: ignore[return-value]
    except Exception:
        return []


# --- Cart: Hash + TTL ---
async def cart_add(client: aioredis.Redis, user_id: str, product_id: int, qty: int) -> int:
    k = keys.cart_key(user_id)
    try:
        await client.hincrby(k, str(product_id), qty)
        await client.expire(k, settings.cart_ttl_s)
        return await client.ttl(k)
    except Exception:
        return -1


async def cart_get(client: aioredis.Redis, user_id: str) -> tuple[dict[int, int], int]:
    k = keys.cart_key(user_id)
    try:
        raw = await client.hgetall(k)
        ttl = await client.ttl(k)
        return {int(p): int(q) for p, q in raw.items()}, ttl
    except Exception:
        return {}, -1
