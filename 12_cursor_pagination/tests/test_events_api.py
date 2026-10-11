"""End-to-end tests for `/events`.

Marked `integration` because they require a populated database.
"""

from __future__ import annotations

import base64
import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_root(client: AsyncClient):
    r = await client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "cursor-pagination"


async def test_healthz(client: AsyncClient):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz(client: AsyncClient):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


async def test_first_page_default_limit(client: AsyncClient):
    r = await client.get("/events")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) > 0
    assert body["has_more"] is True
    assert body["next_cursor"]


async def test_explicit_limit_honoured(client: AsyncClient):
    r = await client.get("/events", params={"limit": 7})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 7


async def test_limit_clamped_to_max(client: AsyncClient):
    # max_page_limit defaults to 500
    r = await client.get("/events", params={"limit": 100000})
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 500


async def test_limit_must_be_positive(client: AsyncClient):
    r = await client.get("/events", params={"limit": 0})
    assert r.status_code == 422


async def test_cursor_advances_and_does_not_repeat(client: AsyncClient):
    """The two consecutive pages should be disjoint and chronologically ordered."""
    r1 = await client.get("/events", params={"limit": 5})
    body1 = r1.json()
    cursor = body1["next_cursor"]
    assert cursor

    r2 = await client.get("/events", params={"limit": 5, "cursor": cursor})
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["items"]) == 5

    ids1 = {it["id"] for it in body1["items"]}
    ids2 = {it["id"] for it in body2["items"]}
    assert ids1.isdisjoint(ids2)

    # Last row of page 1 must come strictly before first row of page 2 in the
    # (created_at, id) order — this is what keyset pagination guarantees.
    last = body1["items"][-1]
    first = body2["items"][0]
    assert (last["created_at"], last["id"]) < (first["created_at"], first["id"])


async def test_full_walk_n_pages(client: AsyncClient):
    """Walk 5 pages and assert ordering + monotonicity across the whole walk."""
    page_size = 50
    cursor: str | None = None
    seen_ids: set[int] = set()
    prev_key: tuple[str, int] | None = None
    for _ in range(5):
        params = {"limit": page_size}
        if cursor:
            params["cursor"] = cursor
        r = await client.get("/events", params=params)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == page_size
        for item in body["items"]:
            key = (item["created_at"], item["id"])
            if prev_key is not None:
                assert key > prev_key
            prev_key = key
            assert item["id"] not in seen_ids
            seen_ids.add(item["id"])
        cursor = body["next_cursor"]
        assert cursor
    assert len(seen_ids) == 5 * page_size


async def test_invalid_cursor_returns_400(client: AsyncClient):
    r = await client.get("/events", params={"cursor": "not-a-cursor!!!"})
    assert r.status_code == 400


async def test_tampered_cursor_returns_400(client: AsyncClient):
    """Valid base64 of invalid JSON should still be rejected."""
    bad = base64.urlsafe_b64encode(b"not json at all").rstrip(b"=").decode()
    r = await client.get("/events", params={"cursor": bad})
    assert r.status_code == 400


async def test_cursor_missing_fields_returns_400(client: AsyncClient):
    """Valid JSON but missing required fields."""
    bad = base64.urlsafe_b64encode(json.dumps({"c": "2024-01-01T00:00:00"}).encode()).rstrip(b"=").decode()
    r = await client.get("/events", params={"cursor": bad})
    assert r.status_code == 400


async def test_status_filter(client: AsyncClient):
    r = await client.get("/events", params={"limit": 25, "status": "paid"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) > 0
    assert all(it["status"] == "paid" for it in body["items"])


async def test_status_filter_no_matches(client: AsyncClient):
    r = await client.get("/events", params={"limit": 25, "status": "definitely-not-a-real-status"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_terminal_page_has_no_next_cursor(client: AsyncClient):
    """Use a cursor that points past the last row — should yield empty + no next."""
    # Far-future timestamp guarantees we sit past every real row.
    far_future = base64.urlsafe_b64encode(
        json.dumps({"c": "2999-01-01T00:00:00", "i": 0}).encode()
    ).rstrip(b"=").decode()
    r = await client.get("/events", params={"limit": 50, "cursor": far_future})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_response_shape(client: AsyncClient):
    r = await client.get("/events", params={"limit": 1})
    item = r.json()["items"][0]
    expected_keys = {
        "id", "order_id", "customer_id", "event_type", "status",
        "amount", "currency", "country", "payment_method",
        "product_sku", "quantity", "created_at", "metadata_",
    }
    assert set(item.keys()) == expected_keys
