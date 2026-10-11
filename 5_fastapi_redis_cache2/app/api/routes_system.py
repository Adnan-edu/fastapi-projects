"""System routes — health / readiness / Redis metrics + TTL inspector."""

from fastapi import APIRouter

from app.core import cache_keys as keys
from app.core.config import settings
from app.core.redis import get_client, ping_redis, redis_info

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    ok = await ping_redis()
    return {"status": "ok" if ok else "degraded", "redis": "up" if ok else "down"}


@router.get("/ready")
async def ready():
    ok = await ping_redis()
    return {"ready": ok}


@router.get("/metrics/redis")
async def redis_metrics():
    client = get_client()
    try:
        dbsize = await client.dbsize()
    except Exception as exc:
        return {"error": str(exc)}
    info = await redis_info("memory")
    stats = await redis_info("stats")
    return {
        "dbsize": dbsize,
        "used_memory_human": info.get("used_memory_human"),
        "connected_clients": (await redis_info("clients")).get("connected_clients"),
        "keyspace_hits": stats.get("keyspace_hits"),
        "keyspace_misses": stats.get("keyspace_misses"),
    }


@router.get("/cache/ttl")
async def cache_ttl(key: str):
    """Learning helper: inspect TTL of any v1 key. Try: key=v1:product:1"""
    client = get_client()
    try:
        ttl = await client.ttl(key)
        exists = await client.exists(key)
        return {"key": key, "exists": bool(exists), "ttl_seconds": ttl,
                "default_product_ttl": settings.cache_ttl_product,
                "default_list_ttl": settings.cache_ttl_list}
    except Exception as exc:
        return {"key": key, "error": str(exc)}


@router.get("/events/subscribe-hint")
async def subscribe_hint():
    return {
        "channel": keys.CHANNEL_PRODUCT_UPDATES,
        "try": f"docker exec {'5_fastapi_redis_cache2-redis-1'} redis-cli SUBSCRIBE {keys.CHANNEL_PRODUCT_UPDATES}",
        "note": "Update a product, then watch the published product id here. "
                "In prod, each API replica subscribes and drops its local copy.",
    }
