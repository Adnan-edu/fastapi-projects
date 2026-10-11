# =====================================================================
# app/services/notification_service.py - Push notification stub
# =====================================================================
# Real implementation would call APNs / FCM. The stub returns a success
# dict so the calling task can build its result payload uniformly.
# =====================================================================

import logging
logger = logging.getLogger(__name__)


class NotificationService:
    """Service for push notifications. Used by both sync API and async ARQ tasks."""

    # Single-user push.
    async def send_push(self, user_id: int, message: str) -> dict:
        logger.info("Sending push notification to user_id=%s: %s", user_id, message)
        return {"user_id": user_id, "message": message, "delivered": True}

    # Bulk push (the task layer usually fans this out to N single-user
    # tasks rather than calling this method directly).
    async def send_batch_push(self, user_ids: list[int], message: str) -> dict:
        logger.info("Sending batch push to %s users", len(user_ids))
        return {"total": len(user_ids), "delivered": True}
