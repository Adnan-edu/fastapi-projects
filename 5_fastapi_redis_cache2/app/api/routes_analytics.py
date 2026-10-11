"""Analytics routes — Counter + Sorted Set + HyperLogLog on real Redis."""

from fastapi import APIRouter, Query

from app.core import cache_keys as keys
from app.core.redis import get_client
from app.services import redis_patterns as pat

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/top-viewed")
async def top_viewed(n: int = Query(default=5, ge=1, le=20)):
    client = get_client()
    rows = await pat.top_viewed(client, n)
    return {"top": [{"product_id": pid, "views": score} for pid, score in rows]}


@router.get("/product/{pid}")
async def product_stats(pid: int):
    client = get_client()
    try:
        views = await client.get(keys.views_key(pid)) or "0"
        try:
            unique = await client.pfcount(keys.visitors_key(pid))
        except Exception:
            unique = 0
        try:
            ttl = await client.ttl(keys.product_key(pid))
        except Exception:
            ttl = -1
        return {"product_id": pid, "views": int(views), "unique_viewers": unique,
                "cached": ttl >= 0, "cache_ttl": ttl}
    except Exception as exc:
        return {"product_id": pid, "error": str(exc)}
