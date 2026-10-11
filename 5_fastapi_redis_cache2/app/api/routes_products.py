"""Product routes — manual cache-aside on real Redis (primary learning path)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis

from app.core import cache_keys as keys
from app.core.cache import invalidate_product
from app.core.config import settings
from app.core.redis import get_client
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.services import product_service as svc
from app.services import redis_patterns as pat

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _ser(p: ProductOut) -> str:
    return json.dumps(p.model_dump(), default=str)


def _de(payload: str) -> dict:
    return json.loads(payload)


async def _cached_or_load(client: aioredis.Redis, key: str, ttl: int, loader) -> tuple[dict, str]:
    """Fail-open cache-aside: Redis errors → load from DB directly."""
    try:
        hit = await client.get(key)
        if hit:
            return (json.loads(hit), "HIT")
    except Exception:
        pass
    data = await loader()
    try:
        await client.set(key, json.dumps(data, default=str), ex=ttl)
    except Exception:
        pass
    return (data, "MISS")


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(data: ProductCreate, request: Request,
                         idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    client = get_client()
    # Idempotency: replay stored response on same key
    if idempotency_key:
        replay = await pat.idempotency_replay(client, idempotency_key)
        if replay:
            return replay
    # Rate limit (per IP, fixed window)
    scope = f"create:{request.client.host if request.client else 'anon'}"
    allowed, _, retry_after = await pat.check_rate_limit(client, scope)
    if not allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Rate limit exceeded",
                            headers={"Retry-After": str(retry_after)})
    p = await svc.create(data)
    await invalidate_product(p.id)
    # Seed autocomplete + tags
    try:
        await client.zadd(keys.AUTOCOMPLETE, {p.name.lower(): 0})
        if p.tags:
            await client.sadd(keys.tags_key(p.id), *p.tags)
    except Exception:
        pass
    if idempotency_key:
        await pat.idempotency_store(client, idempotency_key, json.loads(_ser(p)))
    return p


@router.get("", response_model=list[ProductOut])
async def list_products(response: Response, page: int = Query(default=1, ge=1),
                        size: int = Query(default=20, ge=1, le=100),
                        category: str | None = None, sort: str = "id", q: str | None = None):
    client = get_client()
    query = {"page": page, "size": size, "category": category, "sort": sort, "q": q}
    key = keys.list_key(query)

    async def loader():
        items = await svc.list_products(page=page, size=size, category=category, sort=sort, q=q)
        return [json.loads(_ser(p)) for p in items]

    data, status = await _cached_or_load(client, key, settings.cache_ttl_list, loader)
    response.headers["X-Cache"] = status
    try:
        ttl = await client.ttl(key)
        response.headers["X-Cache-TTL"] = str(ttl)
    except Exception:
        pass
    return data


@router.get("/search", response_model=list[ProductOut])
async def search_products(response: Response, q: str = Query(min_length=1)):
    client = get_client()
    key = keys.search_key(q)

    async def loader():
        return [json.loads(_ser(p)) for p in await svc.search(q)]

    data, status = await _cached_or_load(client, key, settings.cache_ttl_search, loader)
    response.headers["X-Cache"] = status
    return data


@router.get("/featured", response_model=list[ProductOut])
@cache(expire=settings.cache_ttl_featured, namespace="products-featured")
async def featured_products():
    """Decorator path (fastapi-cache2) — contrast with manual cache-aside above."""
    return [json.loads(_ser(p)) for p in await svc.featured()]


@router.get("/autocomplete")
async def autocomplete(prefix: str = Query(min_length=1)):
    """ZSET-based prefix completion. Seed on startup + on product create."""
    client = get_client()
    try:
        members = await client.zrange(keys.AUTOCOMPLETE, 0, -1)
        out = [m for m in members if m.startswith(prefix.lower())][:10]
        return {"prefix": prefix, "suggestions": out}
    except Exception:
        return {"prefix": prefix, "suggestions": []}


@router.get("/{pid}", response_model=ProductOut)
async def get_product(pid: int, response: Response, request: Request,
                      use_lock: bool = Query(default=False, description="Demo stampede lock")):
    client = get_client()
    key = keys.product_key(pid)
    token = str(uuid.uuid4())
    locked = False
    if use_lock:
        locked = await pat.acquire_lock(client, pid, token)
        response.headers["X-Lock"] = "acquired" if locked else "contention-or-redis-down"
    try:
        try:
            hit = await client.get(key)
            if hit:
                response.headers["X-Cache"] = "HIT"
                viewer = request.client.host if request.client else "anon"
                views = await pat.track_view(client, pid, viewer)
                response.headers["X-Views"] = str(views)
                return json.loads(hit)
        except Exception:
            pass  # fail-open: fall through to DB on any Redis error
        p = await svc.get(pid)
        if not p:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Product not found")
        payload = json.loads(_ser(p))
        try:
            await client.set(key, json.dumps(payload), ex=settings.cache_ttl_product)
        except Exception:
            pass
        response.headers["X-Cache"] = "MISS"
        viewer = request.client.host if request.client else "anon"
        views = await pat.track_view(client, pid, viewer)
        response.headers["X-Views"] = str(views)
        return payload
    finally:
        if locked:
            await pat.release_lock(client, pid, token)


@router.put("/{pid}", response_model=ProductOut)
async def update_product(pid: int, data: ProductUpdate):
    p = await svc.update(pid, data)
    if not p:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    await invalidate_product(pid)
    return p


@router.patch("/{pid}", response_model=ProductOut)
async def patch_product(pid: int, data: ProductUpdate):
    return await update_product(pid, data)


@router.delete("/{pid}")
async def delete_product(pid: int):
    ok = await svc.delete(pid)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    await invalidate_product(pid)
    return {"message": f"Product {pid} deleted"}


@router.delete("/cache")
async def clear_product_cache():
    """Demo: SCAN-delete list/search/featured keys (never KEYS)."""
    from app.core.cache import scan_delete

    client = get_client()
    n1 = await scan_delete(client, keys.PRODUCT_LIST_PATTERN)
    n2 = await scan_delete(client, keys.PRODUCT_SEARCH_PATTERN)
    try:
        await client.delete(keys.FEATURED)
    except Exception:
        pass
    return {"message": "Product list/search cache cleared", "removed": n1 + n2}
