import pytest
from starlette.testclient import TestClient

from app.services import user_service


@pytest.fixture(autouse=True)
def reset_store():
    user_service._reset_store()
    yield
    user_service._reset_store()


@pytest.fixture
def app():
    from app.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)