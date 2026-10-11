import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.items import store


@pytest.fixture(autouse=True)
def reset_item_store():
    store._items.clear()
    store._next_id = 1
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac