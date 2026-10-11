# =====================================================================
# tests/test_services.py - Direct unit tests for every service class
# =====================================================================
# These tests bypass the task layer entirely and call services directly.
# Useful for ensuring the business-logic surface remains stable, and as
# documentation of each service's return shape.
# =====================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.email_service import EmailService
from app.services.image_service import ImageService
from app.services.report_service import ReportService
from app.services.payment_service import PaymentService
from app.services.etl_service import ETLService
from app.services.webhook_service import WebhookService
from app.services.notification_service import NotificationService


# --- EmailService -----------------------------------------------------

@pytest.mark.asyncio
async def test_email_service_send_welcome():
    # Verifies the welcome email return shape including email_type.
    service = EmailService()
    result = await service.send_welcome(user_id=1)
    assert result["user_id"] == 1
    assert result["email_type"] == "welcome"
    assert result["sent"] is True


@pytest.mark.asyncio
async def test_email_service_send_report_notification():
    # Report-notification: takes user_id + report_id, returns email_type.
    service = EmailService()
    result = await service.send_report_notification(user_id=2, report_id=5)
    assert result["user_id"] == 2
    assert result["report_id"] == 5
    assert result["email_type"] == "report_notification"


@pytest.mark.asyncio
async def test_email_service_send_batch():
    # Bulk send aggregates the count.
    service = EmailService()
    result = await service.send_batch(user_ids=[1, 2, 3], subject="Test", body="Hello")
    assert result["total"] == 3
    assert result["sent"] is True


# --- ImageService -----------------------------------------------------

@pytest.mark.asyncio
async def test_image_service_create_thumbnail():
    service = ImageService()
    result = await service.create_thumbnail("https://example.com/img.jpg", "200x200")
    # Path is randomised; just assert it's present and the size echoes back.
    assert "thumbnail_path" in result
    assert result["size"] == "200x200"


@pytest.mark.asyncio
async def test_image_service_resize():
    service = ImageService()
    result = await service.resize("https://example.com/img.jpg", "800x600")
    assert "resized_path" in result
    assert result["dimensions"] == "800x600"


# --- ReportService ----------------------------------------------------

@pytest.mark.asyncio
async def test_report_service_generate_pdf():
    service = ReportService()
    result = await service.generate_pdf(report_id=1)
    assert "file_path" in result
    assert result["report_id"] == 1


@pytest.mark.asyncio
async def test_report_service_generate_csv():
    service = ReportService()
    result = await service.generate_csv(query_id=1)
    assert "file_path" in result
    assert result["query_id"] == 1


# --- PaymentService ---------------------------------------------------

@pytest.mark.asyncio
async def test_payment_service_process():
    service = PaymentService()
    result = await service.process(payment_id=1)
    assert result["payment_id"] == 1
    assert result["status"] == "completed"
    # external_id is the fake "pay_xxx" string our stub generates.
    assert "external_id" in result


@pytest.mark.asyncio
async def test_payment_service_refund():
    service = PaymentService()
    result = await service.refund(payment_id=1, reason="Customer request")
    assert result["payment_id"] == 1
    assert result["status"] == "refunded"


# --- ETLService -------------------------------------------------------

@pytest.mark.asyncio
async def test_etl_service_run_pipeline():
    service = ETLService()
    result = await service.run_pipeline("daily_sync")
    assert result["pipeline_name"] == "daily_sync"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_etl_service_sync_data():
    service = ETLService()
    result = await service.sync_data("stripe")
    assert result["source"] == "stripe"
    assert "records_synced" in result


# --- WebhookService ---------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_service_dispatch():
    service = WebhookService()
    result = await service.dispatch("https://example.com/hook", {"event": "test"}, "test")
    assert result["status_code"] == 200


@pytest.mark.asyncio
async def test_webhook_service_retry():
    service = WebhookService()
    result = await service.retry("wh-123")
    assert result["webhook_id"] == "wh-123"
    assert result["status"] == "completed"


# --- NotificationService ----------------------------------------------

@pytest.mark.asyncio
async def test_notification_service_send_push():
    service = NotificationService()
    result = await service.send_push(user_id=1, message="Hello!")
    assert result["user_id"] == 1
    assert result["delivered"] is True


@pytest.mark.asyncio
async def test_notification_service_send_batch_push():
    service = NotificationService()
    result = await service.send_batch_push(user_ids=[1, 2], message="Test")
    assert result["total"] == 2
    assert result["delivered"] is True
