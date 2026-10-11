import pytest
from starlette.testclient import TestClient

from app.core.rate_limit import limiter
from app.services import quote_service


@pytest.fixture(autouse=True)
def reset_state():
    quote_service._reset_store()
    limiter._storage.reset()
    yield
    limiter._storage.reset()
    quote_service._reset_store()


@pytest.fixture
def app():
    from app.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)