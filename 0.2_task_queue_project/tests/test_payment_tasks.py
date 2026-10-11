# =====================================================================
# tests/test_payment_tasks.py - Payment & refund task tests
# =====================================================================

import pytest

from app.tasks.payment_tasks import process_payment, process_refund
from app.services.payment_service import PaymentService


@pytest.mark.asyncio
async def test_process_payment_success():
    # Happy path: gateway stub returns a fake external_id.
    ctx = {"payment_service": PaymentService(), "job_try": 1}
    result = await process_payment(ctx, payment_id=1)
    assert result["payment_id"] == 1
    assert result["status"] == "completed"
    assert "external_id" in result


@pytest.mark.asyncio
async def test_process_payment_retry_on_failure():
    """Test that process_payment raises Retry on failure.

    ARQ Feature: Retry with exponential backoff.
    """
    from arq import Retry
    from unittest.mock import AsyncMock

    # Force gateway timeout so the task takes the except branch.
    mock_service = AsyncMock()
    mock_service.process = AsyncMock(side_effect=Exception("Payment gateway timeout"))

    # job_try=3 → defer = 3 * 10 = 30s → 30000 ms.
    ctx = {"payment_service": mock_service, "job_try": 3}
    with pytest.raises(Retry) as exc_info:
        await process_payment(ctx, payment_id=1)
    assert exc_info.value.defer_score == 30000  # job_try * 10 * 1000 = 3 * 10 * 1000 ms


@pytest.mark.asyncio
async def test_process_refund():
    # Refund with an explicit reason — reason is echoed in the result.
    ctx = {"payment_service": PaymentService()}
    result = await process_refund(ctx, payment_id=1, reason="Customer request")
    assert result["payment_id"] == 1
    assert result["status"] == "refunded"
    assert result["reason"] == "Customer request"


@pytest.mark.asyncio
async def test_process_refund_without_reason():
    # reason=None is explicitly allowed (optional argument).
    ctx = {"payment_service": PaymentService()}
    result = await process_refund(ctx, payment_id=2, reason=None)
    assert result["payment_id"] == 2
    assert result["status"] == "refunded"
    assert result["reason"] is None
