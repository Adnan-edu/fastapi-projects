"""Cart routes — Redis Hash + TTL (ephemeral per-user state)."""

from fastapi import APIRouter

from app.core.redis import get_client
from app.schemas.product import CartItemIn, CartOut
from app.services import redis_patterns as pat

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


@router.post("/{user_id}/items", response_model=CartOut)
async def add_to_cart(user_id: str, item: CartItemIn):
    client = get_client()
    ttl = await pat.cart_add(client, user_id, item.product_id, item.qty)
    items, ttl2 = await pat.cart_get(client, user_id)
    return CartOut(user_id=user_id, items=items, ttl_seconds=ttl2 if ttl2 >= 0 else ttl)


@router.get("/{user_id}", response_model=CartOut)
async def get_cart(user_id: str):
    client = get_client()
    items, ttl = await pat.cart_get(client, user_id)
    return CartOut(user_id=user_id, items=items, ttl_seconds=max(ttl, 0))


@router.delete("/{user_id}")
async def clear_cart(user_id: str):
    from app.core import cache_keys as keys

    client = get_client()
    try:
        await client.delete(keys.cart_key(user_id))
    except Exception:
        pass
    return {"message": f"Cart cleared for {user_id}"}
