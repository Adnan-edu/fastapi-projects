# =====================================================================
# tests/test_webhook_tasks.py - Webhook-task tests (incl. Retry path)
# =====================================================================

import pytest

from app.tasks.webhook_tasks import dispatch_webhook, retry_webhook
from app.services.webhook_service import WebhookService


@pytest.mark.asyncio
async def test_dispatch_webhook_success():
    # Happy path: stubbed service returns status_code 200.
    ctx = {"webhook_service": WebhookService(), "job_try": 1}
    result = await dispatch_webhook(
        ctx,
        url="https://example.com/webhook",
        payload={"event": "order.created"},
        event_type="order",
    )
    assert result["url"] == "https://example.com/webhook"
    assert result["status_code"] == 200


@pytest.mark.asyncio
async def test_dispatch_webhook_retry():
    """Test that dispatch_webhook raises Retry on failure.

    ARQ Feature: Retry with exponential backoff.
    defer = job_try * 5 (5s, 10s, 15s, 20s, 25s)
    """
    from arq import Retry
    from unittest.mock import AsyncMock

    # Force the dispatch to raise — simulates the receiver being down.
    mock_service = AsyncMock()
    mock_service.dispatch = AsyncMock(side_effect=Exception("Connection refused"))

    # job_try=4 → defer = 4 * 5 = 20s → 20000 ms.
    ctx = {"webhook_service": mock_service, "job_try": 4}
    with pytest.raises(Retry) as exc_info:
        await dispatch_webhook(
            ctx,
            url="https://example.com/webhook",
            payload={"event": "test"},
            event_type="test",
        )
    assert exc_info.value.defer_score == 20000  # 4 * 5 * 1000 ms


@pytest.mark.asyncio
async def test_retry_webhook():
    # The retry task just calls the service and returns its summary.
    ctx = {"webhook_service": WebhookService()}
    result = await retry_webhook(ctx, webhook_id="wh-123")
    assert result["webhook_id"] == "wh-123"
    assert result["status"] == "completed"
