# =====================================================================
# app/services/email_service.py - Email sending business logic
# =====================================================================
# In a real app this would call SES/SendGrid/SMTP. Here it's a stub
# that logs and returns a deterministic dict — enough to demonstrate
# the layering pattern (API/task -> service -> external system).
# =====================================================================

import logging

# Module-level logger so log lines show their origin (`app.services...`).
logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails. Used by both sync API and async ARQ tasks."""

    # Welcome-mail entry point. Triggered by send_welcome_email task.
    async def send_welcome(self, user_id: int) -> dict:
        logger.info("Sending welcome email to user_id=%s", user_id)
        # Returning a dict makes the result easy to JSON-encode and
        # store in Redis via ARQ's keep_result.
        return {"user_id": user_id, "email_type": "welcome", "sent": True}

    # Notification fired after a report finishes generating.
    async def send_report_notification(self, user_id: int, report_id: int) -> dict:
        logger.info("Sending report notification to user_id=%s for report_id=%s", user_id, report_id)
        return {"user_id": user_id, "report_id": report_id, "email_type": "report_notification", "sent": True}

    # Batch send — the calling task usually fans this out into one
    # task per user instead of doing a real bulk SMTP send.
    async def send_batch(self, user_ids: list[int], subject: str, body: str) -> dict:
        logger.info("Sending batch email to %s users", len(user_ids))
        return {"total": len(user_ids), "sent": True}
