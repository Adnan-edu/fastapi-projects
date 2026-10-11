# =====================================================================
# app/services/payment_service.py - Payment gateway stub
# =====================================================================
# Represents the integration boundary with Stripe / Braintree / etc.
# The real version would issue HTTP calls and translate gateway-specific
# error codes into our domain enums. This stub fabricates an external id.
# =====================================================================

import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for payment processing. Used by both sync API and async ARQ tasks."""

    # "Charge" a payment by fabricating an external_id like Stripe does.
    async def process(self, payment_id: int) -> dict:
        logger.info("Processing payment_id=%s", payment_id)
        # Real call would be e.g. stripe.PaymentIntent.create(...).
        external_id = f"pay_{uuid.uuid4().hex[:12]}"
        return {"payment_id": payment_id, "external_id": external_id, "status": "completed"}

    # Refund flow — refund_amount is 0.0 because we don't track the
    # actual charged amount here; production would compute it.
    async def refund(self, payment_id: int, reason: str | None = None) -> dict:
        logger.info("Refunding payment_id=%s, reason=%s", payment_id, reason)
        return {"payment_id": payment_id, "refund_amount": 0.0, "reason": reason, "status": "refunded"}
