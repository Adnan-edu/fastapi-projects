# =====================================================================
# app/api/webhooks.py - Webhook registration, dispatch, and retry endpoints
# =====================================================================
# PURPOSE
# -------
# Demonstrates fire-and-forget dispatch (no DB write — just enqueue),
# plus _job_id uniqueness on retries to prevent concurrent retry storms.
# =====================================================================

from fastapi import APIRouter

from app.arq_utils import get_redis_pool
from app.schemas.webhook import WebhookRegister, WebhookPayload

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/register")
async def register_webhook(webhook_in: WebhookRegister):
    """Register a new webhook endpoint.

    In a real application, this would persist the webhook configuration
    to a database. For this demo, we just return the configuration.
    """
    # No-op endpoint — returns the input echoed back. In a real system
    # we'd insert a Webhook row and possibly verify ownership of the URL.
    return {
        "status": "registered",
        "url": webhook_in.url,
        "event_types": webhook_in.event_types,
    }


@router.post("/dispatch")
async def dispatch_webhook_endpoint(webhook_in: WebhookPayload):
    """Dispatch a webhook event.

    ARQ Feature demonstrated: enqueue_job for fire-and-forget async processing.
    Webhooks are dispatched asynchronously via the ARQ worker with
    retry support (Retry exception with exponential backoff).
    """
    redis = await get_redis_pool()
    # Fall back to a placeholder URL if the caller didn't supply one.
    url = webhook_in.url or "https://example.com/webhook"
    # Enqueue the dispatch task. id() yields a per-request unique number
    # so distinct dispatches of the same event type don't collide.
    job = await redis.enqueue_job(
        "dispatch_webhook",
        url,
        webhook_in.payload,
        webhook_in.event_type,
        _job_id=f"webhook_{webhook_in.event_type}_{id(webhook_in)}",
    )
    return {"status": "dispatched", "arq_job_id": job.job_id if job else None}


@router.post("/retry/{webhook_id}")
async def retry_webhook_endpoint(webhook_id: str):
    """Retry a failed webhook delivery.

    ARQ Feature demonstrated: _job_id for uniqueness ensures
    the same webhook is not retried multiple times simultaneously.
    """
    redis = await get_redis_pool()
    # Deterministic _job_id => concurrent retry requests collapse into one.
    job = await redis.enqueue_job(
        "retry_webhook",
        webhook_id,
        _job_id=f"retry_webhook_{webhook_id}",
    )
    return {"status": "retrying", "arq_job_id": job.job_id if job else None}
