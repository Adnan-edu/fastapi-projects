import os

import pytest
from starlette.testclient import TestClient

from app.services import payment_service

os.makedirs("logs", exist_ok=True)


@pytest.fixture(autouse=True)
def reset_state():
    payment_service._reset_store()
    yield
    payment_service._reset_store()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)