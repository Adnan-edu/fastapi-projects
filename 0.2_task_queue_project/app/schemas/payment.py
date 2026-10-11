# =====================================================================
# app/schemas/payment.py - Pydantic schemas for payment endpoints
# =====================================================================

from datetime import datetime
from pydantic import BaseModel


# Request body for POST /payments/process.
class PaymentCreate(BaseModel):
    amount: float           # Money amount; uses float for demo simplicity.
    currency: str = "USD"  # ISO-4217 code.
    user_id: int            # Owning user's primary key.
    description: str | None = None
    # Idempotency key — propagated to ARQ as `_job_id` to deduplicate.
    idempotency_key: str | None = None
    # True (default) -> enqueue ARQ task and return immediately.
    # False           -> call the PaymentService inline (synchronous demo path).
    async_mode: bool = True


# Response for GET /payments/{id} and POST /payments/process.
class PaymentRead(BaseModel):
    id: int
    amount: float
    currency: str
    status: str
    external_id: str | None
    user_id: int
    description: str | None
    idempotency_key: str | None
    created_at: datetime
    processed_at: datetime | None

    # Allow construction directly from a SQLAlchemy Payment instance.
    model_config = {"from_attributes": True}


# Request body for POST /payments/refund.
class RefundRequest(BaseModel):
    payment_id: int
    reason: str | None = None  # Optional human note for audit logs.
