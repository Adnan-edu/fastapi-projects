import pytest
from unittest.mock import AsyncMock

import fakeredis.aioredis
from starlette.testclient import TestClient

from app.core.config import Settings

TEST_SETTINGS = Settings(
    redis_url="redis://localhost:6379/0",
    report_simulated_delay=0.1,
)


@pytest.fixture()
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(fake_redis):
    from app.core import config
    from app.main import create_app
    from app.tasks import report_tasks

    original_settings = config.settings
    config.settings = TEST_SETTINGS

    app = create_app(redis_instance=fake_redis, start_broker=False)

    mock_task_result = AsyncMock()
    mock_task_result.task_id = "test-task-id"

    original_gen_kiq = report_tasks.generate_report.kiq
    original_retry_kiq = report_tasks.generate_report_with_retry.kiq

    report_tasks.generate_report.kiq = AsyncMock(return_value=mock_task_result)
    report_tasks.generate_report_with_retry.kiq = AsyncMock(return_value=mock_task_result)

    c = TestClient(app, raise_server_exceptions=True)
    yield c

    report_tasks.generate_report.kiq = original_gen_kiq
    report_tasks.generate_report_with_retry.kiq = original_retry_kiq
    config.settings = original_settings


@pytest.fixture()
def service(fake_redis):
    from app.services.report_service import ReportService
    return ReportService(fake_redis)