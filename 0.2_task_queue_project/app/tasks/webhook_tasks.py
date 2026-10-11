# =====================================================================
# app/tasks/webhook_tasks.py - ARQ tasks for outbound webhook delivery
# =====================================================================
# Webhooks are inherently unreliable — receivers go down, network
# blips, etc. — so this module leans heavily on Retry with backoff.
# =====================================================================

import json
import logging
from datetime import datetime, timezone

from app.services.webhook_service import WebhookService
from app.tasks._retry import retry_with_backoff

logger = logging.getLogger(__name__)


async def dispatch_webhook(ctx: dict, url: str, payload: dict, event_type: str = "generic") -> dict:
    """Dispatch a webhook to an external URL.

    ARQ Feature: Retry with exponential backoff.
    External webhooks are unreliable, so any HTTP error triggers a retry
    with increasing delay. Uses raise Retry(defer=...) for backoff.
    """
    logger.info("Dispatching webhook to %s for event %s", url, event_type)
    webhook_service = ctx.get("webhook_service", WebhookService())

    try:
        # Real impl would use ctx["http_client"] (set in on_startup) for
        # connection pooling across retries.
        result = await webhook_service.dispatch(url, payload, event_type)
        logger.info("Webhook dispatched to %s: status %s", url, result.get("status_code"))
        return {"url": url, "event_type": event_type, "status_code": result.get("status_code"), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Backoff factor 5s: try1=5, try2=10, ... — modest delay because
        # the most common failure (transient network) usually clears fast.
        logger.warning("Webhook dispatch failed for %s: %s (try %s)", url, e, ctx["job_try"])
        retry_with_backoff(ctx, factor=5)


async def retry_webhook(ctx: dict, webhook_id: str) -> dict:
    """Retry a previously failed webhook delivery.

    ARQ Feature: Custom _job_id for uniqueness.
    The API route enqueues with _job_id=f"retry_webhook_{webhook_id}"
    to prevent duplicate retry jobs for the same webhook.
    """
    logger.info("Retrying webhook delivery for webhook_id=%s", webhook_id)
    webhook_service = ctx.get("webhook_service", WebhookService())
    result = await webhook_service.retry(webhook_id)
    logger.info("Webhook retry completed for webhook_id=%s", webhook_id)
    return {"webhook_id": webhook_id, "status": "completed", "attempts": result.get("attempts", 1), "timestamp": datetime.now(timezone.utc).isoformat()}
