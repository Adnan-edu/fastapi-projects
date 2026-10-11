"""In-memory product store with simulated DB latency.

Keeps the focus on Redis: every read/write sleeps `simulated_db_delay`
so cache HIT vs MISS is measurable. Call counters prove stampede/invalidation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate

_store: dict[int, ProductOut] = {}
_next_id: int = 1
_call_count: dict[str, int] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bump(op: str) -> None:
    _call_count[op] = _call_count.get(op, 0) + 1


def get_call_count(op: str) -> int:
    return _call_count.get(op, 0)


def reset_store() -> None:
    global _store, _next_id, _call_count
    _store = {}
    _next_id = 1
    _call_count = {}
    _seed()


def seed_names() -> list[str]:
    return [p.name for p in _store.values()]


def _seed() -> None:
    global _next_id
    seed = [
        ("Laptop Pro 14", "LP14-001", 1499.0, 25, "electronics", ["laptop", "pro"]),
        ("Ergo Mouse", "EM-002", 49.99, 200, "electronics", ["mouse", "ergo"]),
        ("Standing Desk", "SD-003", 399.0, 40, "furniture", ["desk", "ergo"]),
        ("Coffee Beans 1kg", "CB-004", 19.5, 500, "grocery", ["coffee"]),
    ]
    for name, sku, price, stock, cat, tags in seed:
        p = ProductOut(
            id=_next_id, name=name, sku=sku, price=price, stock=stock,
            category=cat, tags=tags, created_at=_now(), updated_at=_now(),
        )
        _store[_next_id] = p
        _next_id += 1


async def _slow() -> None:
    await asyncio.sleep(settings.simulated_db_delay)


async def create(data: ProductCreate) -> ProductOut:
    global _next_id
    _bump("create")
    await _slow()
    p = ProductOut(id=_next_id, **data.model_dump(), created_at=_now(), updated_at=_now())
    _store[_next_id] = p
    _next_id += 1
    return p


async def get(pid: int) -> ProductOut | None:
    _bump(f"get:{pid}")
    _bump("get")
    await _slow()
    return _store.get(pid)


async def list_products(page: int = 1, size: int = 20, category: str | None = None,
                       sort: str = "id", q: str | None = None) -> list[ProductOut]:
    _bump("list")
    await _slow()
    items = list(_store.values())
    if category:
        items = [p for p in items if p.category == category]
    if q:
        ql = q.lower()
        items = [p for p in items if ql in p.name.lower() or ql in p.sku.lower()]
    if sort == "price":
        items.sort(key=lambda p: p.price)
    elif sort == "-price":
        items.sort(key=lambda p: p.price, reverse=True)
    else:
        items.sort(key=lambda p: p.id)
    start = (page - 1) * size
    return items[start:start + size]


async def update(pid: int, data: ProductUpdate) -> ProductOut | None:
    _bump("update")
    await _slow()
    cur = _store.get(pid)
    if not cur:
        return None
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    merged = cur.model_dump() | patch | {"updated_at": _now()}
    _store[pid] = ProductOut(**merged)
    return _store[pid]


async def delete(pid: int) -> bool:
    _bump("delete")
    await _slow()
    return _store.pop(pid, None) is not None


async def search(q: str) -> list[ProductOut]:
    _bump("search")
    await _slow()
    ql = q.strip().lower()
    return [p for p in _store.values() if ql in p.name.lower() or ql in p.sku.lower()]


async def featured() -> list[ProductOut]:
    _bump("featured")
    await _slow()
    return sorted(_store.values(), key=lambda p: p.id)[:3]


reset_store()
