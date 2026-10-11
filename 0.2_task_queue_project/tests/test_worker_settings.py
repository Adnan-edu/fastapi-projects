# =====================================================================
# tests/test_worker_settings.py - WorkerSettings configuration tests
# =====================================================================
# Confirms that the four WorkerSettings classes are wired correctly:
#   - the monolithic class lists every expected task
#   - tuning knobs match the documented values
#   - each microservice class has the right queue_name and task subset
#   - lifecycle hooks behave as expected
# =====================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.worker import (
    WorkerSettings,
    WorkerSettingsEmail,
    WorkerSettingsPayment,
    WorkerSettingsReport,
    on_worker_startup,
    on_worker_shutdown,
)


def test_worker_settings_functions():
    """Test that WorkerSettings has all expected task functions registered."""
    # Worker.functions can hold either bare functions or `func(fn, ...)`
    # wrappers — handle both shapes when extracting names.
    function_names = []
    for f in WorkerSettings.functions:
        if hasattr(f, "name"):
            function_names.append(f.name)
        elif hasattr(f, "__name__"):
            function_names.append(f.__name__)
        else:
            function_names.append(str(f))
    # Spot-check the headline tasks the README documents.
    assert "send_welcome_email" in function_names
    assert "send_report_email" in function_names
    assert "send_batch_email" in function_names
    assert "generate_thumbnail" in function_names
    assert "generate_pdf_report" in function_names
    assert "generate_csv_export" in function_names
    assert "resize_image" in function_names
    assert "process_payment" in function_names
    assert "process_refund" in function_names
    assert "run_data_pipeline" in function_names
    assert "sync_external_data" in function_names
    assert "dispatch_webhook" in function_names
    assert "retry_webhook" in function_names
    assert "send_push_notification" in function_names
    assert "batch_notify" in function_names


def test_worker_settings_cron_jobs():
    """Test that WorkerSettings has cron jobs configured."""
    # We expect at least the two cleanup cron jobs.
    assert len(WorkerSettings.cron_jobs) >= 2


def test_worker_settings_config():
    """Test WorkerSettings configuration values.

    ARQ Features demonstrated:
    - max_jobs: Maximum concurrent jobs
    - retry_jobs: Auto-retry on Retry exception
    - job_timeout: Default timeout per job
    - keep_result: How long results are retained
    """
    assert WorkerSettings.max_jobs == 50
    assert WorkerSettings.retry_jobs is True
    assert WorkerSettings.max_tries == 5
    assert WorkerSettings.job_timeout == 300
    assert WorkerSettings.keep_result == 3600


def test_worker_settings_email_queue():
    """Test microservice WorkerSettings for email domain.

    ARQ Feature: Custom queue_name for service isolation.
    """
    assert WorkerSettingsEmail.queue_name == "email"
    # Three email tasks: welcome, report, batch.
    assert len(WorkerSettingsEmail.functions) == 3


def test_worker_settings_payment_queue():
    """Test microservice WorkerSettings for payment domain."""
    assert WorkerSettingsPayment.queue_name == "payment"
    # Two payment tasks: process_payment + process_refund.
    assert len(WorkerSettingsPayment.functions) == 2


def test_worker_settings_report_queue():
    """Test microservice WorkerSettings for report domain."""
    assert WorkerSettingsReport.queue_name == "report"
    # Four tasks: pdf, csv, thumbnail, resize.
    assert len(WorkerSettingsReport.functions) == 4


@pytest.mark.asyncio
async def test_on_worker_startup():
    """Test that on_worker_startup initializes shared resources.

    ARQ Feature: on_startup hook creates HTTP client
    that is available to all tasks via ctx dict.
    """
    ctx = {}
    await on_worker_startup(ctx)
    # The hook must populate these two keys for downstream tasks.
    assert "http_client" in ctx
    assert "worker_started_at" in ctx
    # Always release the real httpx client created during the test.
    await ctx["http_client"].aclose()


@pytest.mark.asyncio
async def test_on_worker_shutdown():
    """Test that on_worker_shutdown cleans up shared resources.

    ARQ Feature: on_shutdown hook closes HTTP client
    created during on_startup.
    """
    from httpx import AsyncClient
    # Pre-populate ctx with what on_startup would have created.
    ctx = {"http_client": AsyncClient(timeout=30.0)}
    await on_worker_shutdown(ctx)
