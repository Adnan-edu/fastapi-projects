# =====================================================================
# tests/test_cleanup_tasks.py - Cron-job cleanup task tests
# =====================================================================
# Exercise the two scheduled cleanup tasks WITHOUT touching the real DB.
# We patch `async_session` to a context-manager-shaped AsyncMock so the
# `async with async_session() as session:` block inside the task hits
# our stub session, whose execute() returns a mock result with rowcount.
# =====================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_cleanup_expired_sessions():
    """Test cron job: cleanup_expired_sessions.

    ARQ Feature: Cron jobs defined with @cron decorator.
    This task runs on a schedule (every hour) and at worker startup.
    """
    # Mimic the SQLAlchemy Result.rowcount attribute the task reads.
    mock_result = MagicMock()
    mock_result.rowcount = 5

    # Build a session that behaves as both an async context manager AND
    # has awaitable execute()/commit(). __aenter__/__aexit__ are wired
    # so `async with async_session() as session:` yields THIS mock.
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    # Patch where async_session is LOOKED UP (inside the task module),
    # not where it's defined.
    with patch("app.tasks.cleanup_tasks.async_session", return_value=mock_session):
        from app.tasks.cleanup_tasks import cleanup_expired_sessions
        ctx = {}
        result = await cleanup_expired_sessions(ctx)
    # The task returns a dict with these two keys regardless of rowcount.
    assert "expired_sessions_removed" in result
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_cleanup_old_job_results():
    """Test cron job: cleanup_old_job_results.

    ARQ Feature: Cron jobs with unique=True to prevent concurrent runs.
    Runs daily at 2 AM.
    """
    # Same mock-session pattern as the previous test; different rowcount.
    mock_result = MagicMock()
    mock_result.rowcount = 10

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.tasks.cleanup_tasks.async_session", return_value=mock_session):
        from app.tasks.cleanup_tasks import cleanup_old_job_results
        ctx = {}
        result = await cleanup_old_job_results(ctx)
    assert "old_jobs_removed" in result
    assert "timestamp" in result
