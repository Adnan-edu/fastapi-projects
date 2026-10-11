# =====================================================================
# app/models/payment.py - Payment transactions
# =====================================================================
# PURPOSE
# -------
# Persists every payment attempt. The combination of `idempotency_key`
# + `_job_id` in the API route (see app/api/payments.py) gives us
# exactly-once payment processing even if the client retries.
# =====================================================================

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Lifecycle states a Payment row moves through.
class PaymentStatus(str, enum.Enum):
    PENDING = "pending"        # Row created, not yet sent to gateway
    PROCESSING = "processing"  # Worker picked it up and is calling the gateway
    COMPLETED = "completed"    # Gateway returned success
    FAILED = "failed"           # Gateway returned failure / retries exhausted
    REFUNDED = "refunded"       # Originally completed, later refunded


class Payment(Base):
    __tablename__ = "payments"

    # Auto-increment surrogate key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Money amount as a float — fine for the demo; prefer Numeric/Decimal in real systems.
    amount: Mapped[float] = mapped_column(Float)
    # ISO-4217 currency code, defaulted to USD.
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Lifecycle state — see PaymentStatus above.
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    # ID returned by the upstream payment gateway (Stripe, etc.). Unique
    # so we never insert the same external transaction twice.
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    # FK to the user who initiated the payment.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    # Free-text description shown on receipts.
    description: Mapped[str | None] = mapped_column(String(500))
    # Client-supplied idempotency key. Combined with ARQ's `_job_id`
    # this guarantees the same logical payment runs exactly once.
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    # When the row was inserted.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # When the worker finished processing (success or refund).
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # ORM back-reference to the owning User. Pairs with User.payments.
    user: Mapped["User"] = relationship(back_populates="payments")
