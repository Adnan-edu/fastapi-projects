import os

import pytest
from starlette.testclient import TestClient

from app.services import document_service


@pytest.fixture(autouse=True)
def reset_state():
    document_service._reset_store()
    yield
    document_service._reset_store()


@pytest.fixture
def client():
    os.makedirs("logs", exist_ok=True)
    from app.main import app
    return TestClient(app)