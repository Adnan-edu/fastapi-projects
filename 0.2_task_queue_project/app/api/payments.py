# =====================================================================
# app/api/payments.py - Payment endpoints (process / refund / list / get)
# =====================================================================
# PURPOSE
# -------
# Demonstrates the most production-relevant ARQ features:
#   - Idempotency via `_job_id` + a unique idempotency_key column
#   - Per-domain queue routing via `_queue_name="payment"` (microservice)
#   - Dual sync/async mode toggle for testing without a worker
# =====================================================================

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.arq_utils import get_redis_pool
from app.models import Payment, PaymentStatus, User
from app.schemas.payment import PaymentCreate, PaymentRead, RefundRequest

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/process", response_model=PaymentRead)
async def process_payment_endpoint(payment_in: PaymentCreate, db: AsyncSession = Depends(get_db)):
    """Process a payment. Uses ARQ queue when async_mode=True.

    ARQ Features demonstrated:
    - _job_id with idempotency_key for exactly-once processing
    - async_mode=True: enqueue_job for background processing
    - async_mode=False: Call service directly
    """
    # ---- 1. Validate user exists ----------------------------------
    result = await db.execute(select(User).where(User.id == payment_in.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---- 2. Idempotency short-circuit -----------------------------
    # If the client supplied an idempotency key AND a Payment row with
    # that key already exists, return it instead of creating a duplicate.
    if payment_in.idempotency_key:
        result = await db.execute(
            select(Payment).where(Payment.idempotency_key == payment_in.idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    # ---- 3. Insert pending Payment row ----------------------------
    payment = Payment(
        amount=payment_in.amount,
        currency=payment_in.currency,
        user_id=payment_in.user_id,
        description=payment_in.description,
        idempotency_key=payment_in.idempotency_key,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # ---- 4. Async vs sync mode ------------------------------------
    if payment_in.async_mode:
        # Async path: enqueue the heavy lifting on the payment worker.
        redis = await get_redis_pool()
        # _job_id ensures ARQ-level dedup: the same key cannot be queued
        # twice while the first attempt is alive in Redis.
        job_id = payment_in.idempotency_key or f"payment_{payment.id}"
        await redis.enqueue_job(
            "process_payment",
            payment.id,
            _job_id=job_id,
            _queue_name="payment",  # Microservice mode: route to payment worker.
        )
    else:
        # Sync path: useful for unit tests / curl debugging without a worker.
        from app.services.payment_service import PaymentService
        payment_service = PaymentService()
        result = await payment_service.process(payment.id)
        payment.status = PaymentStatus.COMPLETED
        payment.external_id = result.get("external_id")
        payment.processed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(payment)

    return payment


@router.post("/refund", response_model=PaymentRead)
async def refund_payment(refund_in: RefundRequest, db: AsyncSession = Depends(get_db)):
    """Refund a completed payment.

    ARQ Feature demonstrated: _defer_until for scheduled refunds.
    The query parameter 'schedule' can set a future datetime for deferred processing.
    """
    # Pull the payment by id.
    result = await db.execute(select(Payment).where(Payment.id == refund_in.payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    # Business rule: we only refund completed payments.
    if payment.status != PaymentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Payment is not in completed status")

    # Enqueue the refund job. The deterministic _job_id (one per payment)
    # prevents two refund attempts from racing against each other.
    redis = await get_redis_pool()
    await redis.enqueue_job(
        "process_refund",
        payment.id,
        refund_in.reason,
        _job_id=f"refund_{payment.id}",
    )

    # Optimistically mark as refunded — the worker will overwrite this
    # if the gateway rejects the refund.
    payment.status = PaymentStatus.REFUNDED
    payment.processed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(payment)

    return payment


@router.get("/", response_model=list[PaymentRead])
async def list_payments(db: AsyncSession = Depends(get_db)):
    # Newest first; no pagination for demo.
    result = await db.execute(select(Payment).order_by(Payment.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(payment_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment
