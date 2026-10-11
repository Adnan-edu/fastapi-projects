# =====================================================================
# tests/test_etl_tasks.py - ETL task unit tests
# =====================================================================
# Covers success paths AND the Retry backoff branch. The retry test is
# a particularly useful template — it shows how to assert defer values
# without a real worker loop.
# =====================================================================

import pytest

from app.tasks.etl_tasks import run_data_pipeline, sync_external_data
from app.services.etl_service import ETLService


@pytest.mark.asyncio
async def test_run_data_pipeline():
    # Happy path: real (stub) ETLService returns rows_processed.
    ctx = {"etl_service": ETLService()}
    result = await run_data_pipeline(ctx, pipeline_name="daily_user_sync")
    assert result["pipeline_name"] == "daily_user_sync"
    assert result["status"] == "completed"
    assert "rows_processed" in result


@pytest.mark.asyncio
async def test_sync_external_data_success():
    # Happy path for sync_external_data. job_try=1 indicates first attempt.
    ctx = {"etl_service": ETLService(), "job_try": 1}
    result = await sync_external_data(ctx, source="stripe")
    assert result["source"] == "stripe"
    assert result["status"] == "completed"
    assert "records_synced" in result


@pytest.mark.asyncio
async def test_sync_external_data_retry():
    """Test that sync_external_data raises Retry on failure.

    ARQ Feature: Retry with exponential backoff for flaky external APIs.
    defer = job_try * 8 (8s, 16s, 24s, 32s, 40s)
    """
    from arq import Retry
    from unittest.mock import AsyncMock

    # Force the service to raise — simulates a downstream outage.
    mock_service = AsyncMock()
    mock_service.sync_data = AsyncMock(side_effect=ConnectionError("API unavailable"))

    # job_try=2 -> task should raise Retry(defer=16).
    ctx = {"etl_service": mock_service, "job_try": 2}
    with pytest.raises(Retry) as exc_info:
        await sync_external_data(ctx, source="stripe")
    # ARQ stores defer internally in milliseconds (defer_score).
    assert exc_info.value.defer_score == 16000  # 2 * 8 * 1000 ms
