# =====================================================================
# app/schemas/webhook.py - Pydantic schemas for /webhooks endpoints
# =====================================================================

from pydantic import BaseModel


# Request body for POST /webhooks/register. Demo-only: not persisted.
class WebhookRegister(BaseModel):
    url: str                # Where the webhook should be POSTed.
    event_types: list[str]  # Which events this subscription wants.
    secret: str | None = None  # Optional HMAC secret for signing.


# Request body for POST /webhooks/dispatch.
class WebhookPayload(BaseModel):
    event_type: str        # e.g. "order.created"
    payload: dict          # Arbitrary JSON body to POST.
    url: str | None = None  # Override the destination URL (otherwise defaults).
    webhook_id: str | None = None  # Optional logical id for retry workflows.
