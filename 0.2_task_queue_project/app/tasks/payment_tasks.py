# =====================================================================
# app/tasks/payment_tasks.py - ARQ tasks for payment processing
# =====================================================================
# Payments are the canonical example of where ARQ shines:
#   - Slow upstream (gateway API call) -> background work
#   - Must run exactly once         -> idempotency via _job_id
#   - May fail transiently           -> Retry with backoff
#   - Can be scheduled               -> _defer_until for trial endings
# =====================================================================

import logging
from datetime import datetime, timezone, timedelta

from app.services.payment_service import PaymentService
from app.tasks._retry import retry_with_backoff

logger = logging.getLogger(__name__)


async def process_payment(ctx: dict, payment_id: int) -> dict:
    """Process a payment through an external payment gateway.

    ARQ Feature: Idempotency via _job_id.
    The API route enqueues this task with _job_id=f"payment_{idempotency_key}"
    to ensure the same payment is never processed twice.

    ARQ Feature: func() wrapper with max_tries=3.
    Only 3 attempts before permanent failure.
    """
    logger.info("Processing payment id=%s (try %s)", payment_id, ctx["job_try"])
    payment_service = ctx.get("payment_service", PaymentService())

    try:
        # Call the (stubbed) gateway. In production this is the slow,
        # network-bound work that justified offloading to a worker.
        result = await payment_service.process(payment_id)
        logger.info("Payment id=%s processed successfully", payment_id)
        return {"payment_id": payment_id, "status": "completed", "external_id": result.get("external_id"), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Gateway flake → tell ARQ to retry with backoff:
        #   try1=10s, try2=20s, try3=30s. After max_tries → permanent fail.
        logger.warning("Payment id=%s failed: %s (try %s)", payment_id, e, ctx["job_try"])
        retry_with_backoff(ctx, factor=10)


async def process_refund(ctx: dict, payment_id: int, reason: str | None = None) -> dict:
    """Process a refund for a completed payment.

    ARQ Feature: Deferred execution with _defer_until.
    The API route can schedule a refund for a future date:
      enqueue_job('process_refund', payment_id, reason, _defer_until=future_date)
    This is useful for trial cancellations that take effect at end of billing period.
    """
    logger.info("Processing refund for payment_id=%s, reason=%s", payment_id, reason)
    payment_service = ctx.get("payment_service", PaymentService())
    # No retry/backoff here — refunds usually need human intervention
    # if they fail. We let the exception bubble so it ends up in the
    # JobLog as FAILED.
    result = await payment_service.refund(payment_id, reason)
    logger.info("Refund processed for payment_id=%s", payment_id)
    return {"payment_id": payment_id, "status": "refunded", "refund_amount": result.get("refund_amount"), "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()}
