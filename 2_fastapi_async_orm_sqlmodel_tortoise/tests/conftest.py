import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise
from tortoise.config import AppConfig, DBUrlConfig, TortoiseConfig

from app.core.config import settings


TEST_DB_URL = "sqlite://:memory:"

TEST_TORTOISE_ORM = TortoiseConfig(
    connections={"default": DBUrlConfig(url=TEST_DB_URL)},
    apps={
        "models": AppConfig(
            models=["app.models"],
            default_connection="default",
        ),
    },
)


@pytest.fixture(scope="session")
def app():
    from app.main import create_app
    return create_app()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await Tortoise.init(config=TEST_TORTOISE_ORM)
    await Tortoise.generate_schemas()
    yield
    await Tortoise._drop_databases()
    await Tortoise.close_connections()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac