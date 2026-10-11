# =====================================================================
# tests/test_email_tasks.py - Email-task unit tests
# =====================================================================
# Test the email ARQ tasks directly (no Redis, no worker process).
# We just call the async function with a hand-built ctx dict.
# =====================================================================

import pytest

from app.tasks.email_tasks import send_welcome_email, send_report_email, send_batch_email
from app.services.email_service import EmailService


@pytest.mark.asyncio
async def test_send_welcome_email():
    # Provide a real EmailService in ctx so the task uses it instead of
    # constructing a new one. Verifies the happy path.
    ctx = {"email_service": EmailService()}
    result = await send_welcome_email(ctx, user_id=1)
    assert result["user_id"] == 1
    assert result["email_sent"] is True
    # `timestamp` is added by the task (not the service) — proves the
    # task layer composed the response correctly.
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_send_welcome_email_without_service():
    # Empty ctx forces the task's ctx.get(..., EmailService()) default
    # branch to fire. Same observable behaviour as the previous test.
    ctx = {}
    result = await send_welcome_email(ctx, user_id=42)
    assert result["user_id"] == 42
    assert result["email_sent"] is True


@pytest.mark.asyncio
async def test_send_report_email():
    # Report email takes two positional args (user_id, report_id).
    ctx = {"email_service": EmailService()}
    result = await send_report_email(ctx, user_id=1, report_id=10)
    assert result["user_id"] == 1
    assert result["report_id"] == 10
    assert result["email_sent"] is True


@pytest.mark.asyncio
async def test_send_batch_email():
    # Fan-out test: batch_email must call redis.enqueue_job once per user.
    from unittest.mock import AsyncMock, MagicMock

    # Mock the Redis pool so the task can "enqueue" jobs without Redis.
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "batch-job-1"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"redis": mock_redis, "email_service": EmailService()}
    result = await send_batch_email(ctx, user_ids=[1, 2, 3], subject="Test", body="Hello")
    # 3 users -> 3 enqueue calls, all reported.
    assert result["total"] == 3
    assert result["enqueued"] == 3
    assert mock_redis.enqueue_job.call_count == 3
