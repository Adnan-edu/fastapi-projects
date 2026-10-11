# =====================================================================
# tests/test_report_tasks.py - Report-task tests (incl. task chaining)
# =====================================================================
# Verifies that after generating a PDF/CSV, the task enqueues a
# follow-up send_report_email job — the chaining contract.
# =====================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.tasks.report_tasks import generate_pdf_report, generate_csv_export
from app.services.report_service import ReportService


@pytest.mark.asyncio
async def test_generate_pdf_report():
    # Happy path: report generation returns file_path and chains an email.
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "email-job-1"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"report_service": ReportService(), "redis": mock_redis}
    result = await generate_pdf_report(ctx, report_id=5)
    assert result["report_id"] == 5
    assert result["status"] == "completed"
    assert "file_path" in result


@pytest.mark.asyncio
async def test_generate_pdf_report_chains_email():
    """Test that PDF report generation enqueues a follow-up email task.

    ARQ Feature: Task chaining - one task enqueues another.
    """
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "email-job-1"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"report_service": ReportService(), "redis": mock_redis}
    result = await generate_pdf_report(ctx, report_id=5)

    # Exactly one chained enqueue.
    mock_redis.enqueue_job.assert_called_once()
    call_args = mock_redis.enqueue_job.call_args
    # Positional arg 0 is the task name — must be the follow-up email.
    assert call_args[0][0] == "send_report_email"
    # Must include the _defer_by kwarg so the email is delayed.
    assert "_defer_by" in call_args[1]


@pytest.mark.asyncio
async def test_generate_csv_export():
    # CSV happy path — same structure as PDF but different defer (30s).
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "email-job-2"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"report_service": ReportService(), "redis": mock_redis}
    result = await generate_csv_export(ctx, query_id=10)
    assert result["query_id"] == 10
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_generate_csv_export_chains_email():
    """Test that CSV export enqueues a follow-up email task."""
    mock_redis = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "email-job-3"
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    ctx = {"report_service": ReportService(), "redis": mock_redis}
    await generate_csv_export(ctx, query_id=10)

    # The chained email task must have been enqueued exactly once.
    mock_redis.enqueue_job.assert_called_once()
    call_args = mock_redis.enqueue_job.call_args
    assert call_args[0][0] == "send_report_email"
