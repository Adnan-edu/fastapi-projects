from datetime import datetime, timezone

_ORDERS: list[dict] = [
    {"id": 1, "customer": "Alice", "item": "Widget", "quantity": 3, "status": "pending", "created_at": "2025-01-01T10:00:00Z"},
    {"id": 2, "customer": "Bob", "item": "Gadget", "quantity": 1, "status": "shipped", "created_at": "2025-01-02T11:30:00Z"},
    {"id": 3, "customer": "Carol", "item": "Doohickey", "quantity": 5, "status": "delivered", "created_at": "2025-01-03T09:15:00Z"},
]

_next_id = len(_ORDERS) + 1


def create(customer: str, item: str, quantity: int) -> dict:
    global _next_id
    order = {
        "id": _next_id,
        "customer": customer,
        "item": item,
        "quantity": quantity,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _ORDERS.append(order)
    _next_id += 1
    return order


def get_all() -> list[dict]:
    return list(_ORDERS)


def get_by_id(order_id: int) -> dict | None:
    for order in _ORDERS:
        if order["id"] == order_id:
            return order
    return None


def _reset_store() -> None:
    global _ORDERS, _next_id
    _ORDERS = [
        {"id": 1, "customer": "Alice", "item": "Widget", "quantity": 3, "status": "pending", "created_at": "2025-01-01T10:00:00Z"},
        {"id": 2, "customer": "Bob", "item": "Gadget", "quantity": 1, "status": "shipped", "created_at": "2025-01-02T11:30:00Z"},
        {"id": 3, "customer": "Carol", "item": "Doohickey", "quantity": 5, "status": "delivered", "created_at": "2025-01-03T09:15:00Z"},
    ]
    _next_id = len(_ORDERS) + 1
