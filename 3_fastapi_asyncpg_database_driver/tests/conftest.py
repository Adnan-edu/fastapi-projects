import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.db import close_db, connect_db, get_pool


@pytest.fixture(scope="session")
def app():
    from app.main import create_app
    return create_app()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await connect_db()
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM products")
    yield
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM products")
    await close_db()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac