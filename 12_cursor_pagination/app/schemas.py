from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    customer_id: int
    event_type: str
    status: str
    amount: Decimal
    currency: str
    country: str
    payment_method: str
    product_sku: str
    quantity: int
    created_at: datetime
    metadata_: str | None = None


class EventsPage(BaseModel):
    items: list[OrderEventOut]
    next_cursor: str | None = None
    has_more: bool
