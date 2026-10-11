# =====================================================================
# app/services/webhook_service.py - Outbound webhook delivery stub
# =====================================================================
# In production this would use httpx.AsyncClient (via ctx["http_client"]
# from the worker's on_startup hook) to POST the payload, then translate
# HTTP errors into Retry exceptions in the task layer.
# =====================================================================

import json
import logging

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for webhook dispatch. Used by both sync API and async ARQ tasks."""

    # Pretend to POST `payload` to `url`. Returns a 200 result so tasks
    # see a success path; real impl would surface real status codes.
    async def dispatch(self, url: str, payload: dict, event_type: str = "generic") -> dict:
        logger.info("Dispatching webhook to %s for event %s", url, event_type)
        return {"url": url, "status_code": 200, "event_type": event_type, "response_body": "ok"}

    # Redelivers a previously failed webhook by id.
    async def retry(self, webhook_id: str) -> dict:
        logger.info("Retrying webhook_id=%s", webhook_id)
        return {"webhook_id": webhook_id, "attempts": 1, "status": "completed"}
