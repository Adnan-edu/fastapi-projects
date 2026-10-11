"""Central Redis key schemas (versioned). Production rule: SCAN, never KEYS."""

from __future__ import annotations

import hashlib
import json

V = "v1"

# --- Products ---
PRODUCT = f"{V}:product:{{pid}}"                      # String(JSON) + EXPIRE
PRODUCT_LIST = f"{V}:products:list:{{qh}}"            # String(JSON) short TTL
PRODUCT_SEARCH = f"{V}:products:search:{{norm}}"      # String(JSON)
PRODUCT_VIEWS = f"{V}:product:{{pid}}:views"          # Counter (INCR)
PRODUCT_VISITORS = f"{V}:visitors:{{pid}}"            # HyperLogLog
LEADERBOARD_VIEWS = f"{V}:leaderboard:views"          # ZSET product_id -> views
FEATURED = f"{V}:products:featured"                   # String(JSON)

# --- Cart (Hash + TTL) ---
CART = f"{V}:cart:{{user_id}}"                        # Hash product_id -> qty

# --- Reliability patterns ---
IDEMPOTENCY = f"{V}:idempotency:{{key}}"              # String(JSON) NX EX 24h
RATELIMIT = f"{V}:ratelimit:{{scope}}:{{window}}"     # Counter INCR + EXPIRE
LOCK_PRODUCT = f"{V}:lock:product:{{pid}}"            # String NX PX (stampede guard)

# --- Discovery ---
AUTOCOMPLETE = f"{V}:autocomplete"                    # ZSET member -> score(0)
PRODUCT_TAGS = f"{V}:product:{{pid}}:tags"            # SET

# --- Pub/Sub ---
CHANNEL_PRODUCT_UPDATES = f"{V}:events:product-updates"

# --- List/search invalidation scan patterns ---
PRODUCT_LIST_PATTERN = f"{V}:products:list:*"
PRODUCT_SEARCH_PATTERN = f"{V}:products:search:*"


def product_key(pid: int | str) -> str:
    return PRODUCT.format(pid=pid)


def list_key(query: dict) -> str:
    raw = json.dumps(query, sort_keys=True, default=str)
    qh = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return PRODUCT_LIST.format(qh=qh)


def search_key(q: str) -> str:
    return PRODUCT_SEARCH.format(norm=q.strip().lower())


def views_key(pid: int | str) -> str:
    return PRODUCT_VIEWS.format(pid=pid)


def visitors_key(pid: int | str) -> str:
    return PRODUCT_VISITORS.format(pid=pid)


def cart_key(user_id: str) -> str:
    return CART.format(user_id=user_id.strip().lower())


def idempotency_key(key: str) -> str:
    return IDEMPOTENCY.format(key=key)


def ratelimit_key(scope: str, window: int) -> str:
    return RATELIMIT.format(scope=scope, window=window)


def lock_key(pid: int | str) -> str:
    return LOCK_PRODUCT.format(pid=pid)


def tags_key(pid: int | str) -> str:
    return PRODUCT_TAGS.format(pid=pid)
