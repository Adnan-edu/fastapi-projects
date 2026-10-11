"""Unit tests for idempotency key derivation. No infra needed."""

from app.ids import idempotency_key


def test_idempotency_key_stable():
    """Test 1 — same filters → same key, always."""

    f = {"status": "paid", "country": "US"}
    assert idempotency_key(f) == idempotency_key(f) == idempotency_key(dict(f))


def test_idempotency_key_order_invariant():
    """Test 2 — key order in the input dict must not affect the hash."""

    a = {"status": "paid", "country": "US"}
    b = {"country": "US", "status": "paid"}
    assert idempotency_key(a) == idempotency_key(b)


def test_idempotency_key_drops_none():
    """``status=None`` and an omitted ``status`` are the same request."""

    assert idempotency_key({"status": "paid"}) == idempotency_key(
        {"status": "paid", "country": None}
    )


def test_idempotency_key_distinct_for_distinct_filters():
    assert idempotency_key({"status": "paid"}) != idempotency_key({"status": "failed"})
