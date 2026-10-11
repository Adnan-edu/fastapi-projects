# =====================================================================
# tests/test_notification_tasks.py - Push-notification + fan-out tests
# =====================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.tasks.notification_tasks import send_push_notification, batch_notify
from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_send_push_notification():
    # Happy path with a real (stub) NotificationService.
    ctx = {"notification_service": NotificationService()}
    result = await send_push_notification(ctx, user_id=1, message="Hello!")
    assert result["user_id"] == 1
    assert result["sent"] is True


@pytest.mark.asyncio
async def test_send_push_notification_without_service():
    # Empty ctx triggers the default-service fallback inside the task.
    ctx = {}
    result = await send_push_notification(ctx, user_id=99, message="Test")
    assert result["user_id"] == 99
    assert result["sent"] is True


@pytest.mark.asyncio
async def test_batch_notify_fan_out():
    """Test fan-out pattern: batch_notify enqueues individual tasks.

    ARQ Feature: Fan-out - one task enqueues many sub-tasks.
    """
    # Every enqueue_job call returns the same MagicMock job for simplicity.
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "push-job-1"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"redis": mock_redis}
    result = await batch_notify(ctx, user_ids=[1, 2, 3, 4, 5], message="New feature!")
    # 5 users in → 5 enqueue calls out → all 5 reported.
    assert result["total_users"] == 5
    assert result["enqueued"] == 5
    assert mock_redis.enqueue_job.call_count == 5

    # Every enqueued task name must be "send_push_notification".
    for call in mock_redis.enqueue_job.call_args_list:
        assert call[0][0] == "send_push_notification"


@pytest.mark.asyncio
async def test_batch_notify_with_some_failures():
    """Test fan-out when some enqueue_job calls return None (duplicate _job_id)."""
    mock_redis = AsyncMock()

    # side_effect cycles through these values for each call. None
    # simulates "dedup collapsed the job" (returning None).
    results = [MagicMock(job_id=f"push-{i}") if i < 3 else None for i in range(5)]
    mock_redis.enqueue_job = AsyncMock(side_effect=results)

    ctx = {"redis": mock_redis}
    result = await batch_notify(ctx, user_ids=[1, 2, 3, 4, 5], message="Test")
    # total_users counts the input list; enqueued only counts NON-None returns.
    assert result["total_users"] == 5
    assert result["enqueued"] == 3  # Only 3 succeeded
