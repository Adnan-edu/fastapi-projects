import pytest
from starlette.testclient import TestClient

from app.services import order_service


@pytest.fixture(autouse=True)
def reset_state():
    order_service._reset_store()
    yield
    order_service._reset_store()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)
