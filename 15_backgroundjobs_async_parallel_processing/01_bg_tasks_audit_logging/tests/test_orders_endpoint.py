"""Endpoint behaviour: status codes, payload shape, query handling."""

from __future__ import annotations

from tests.conftest import FakeRow


def test_orders_returns_empty_list_when_no_rows(client):
    r = client.get("/orders")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "items": []}


def test_orders_serializes_rows(client, fake_session):
    fake_session.rows = [
        FakeRow(id=1, order_id=10, customer_id=100, status="paid", amount="9.99"),
        FakeRow(id=2, order_id=11, customer_id=100, status="paid", amount="19.50"),
    ]
    r = client.get("/orders?status=paid&limit=10")
    body = r.json()
    assert r.status_code == 200
    assert body["count"] == 2
    assert body["items"] == [
        {"id": 1, "order_id": 10, "status": "paid", "amount": "9.99"},
        {"id": 2, "order_id": 11, "status": "paid", "amount": "19.50"},
    ]


def test_orders_rejects_limit_above_max(client):
    r = client.get("/orders?limit=501")
    assert r.status_code == 422


def test_orders_rejects_non_integer_customer_id(client):
    r = client.get("/orders?customer_id=not-a-number")
    assert r.status_code == 422
