import pytest
from starlette.testclient import TestClient

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from app.core.cache import city_key_builder
from app.core.config import Settings
from app.services import weather_service


def pytest_addoption(parser):
    parser.addoption("--redis", action="store_true", default=False,
                     help="Run tests against real Docker Redis (db 15)")


TEST_SETTINGS = Settings(
    redis_url="redis://localhost:6379/15",
    cache_ttl=10,
    weather_simulated_delay=0.1,
    simulated_db_delay=0.05,
    cache_prefix="test-cache",
    cache_ttl_product=60,
    cache_ttl_list=15,
)


@pytest.fixture(autouse=True)
def _reset_shared_state():
    FastAPICache.reset()
    InMemoryBackend._store.clear()
    yield
    InMemoryBackend._store.clear()
    FastAPICache.reset()


@pytest.fixture()
def client():
    from app.main import create_app
    from app.core import config

    original_settings = config.settings
    config.settings = TEST_SETTINGS
    import app.api.routes_weather
    import app.services.weather_service
    import app.core.cache
    app.api.routes_weather.settings = TEST_SETTINGS
    app.services.weather_service.settings = TEST_SETTINGS
    app.core.cache.settings = TEST_SETTINGS

    weather_service._reset_call_count()

    from app.services import product_service
    import app.api.routes_products
    import app.services.redis_patterns
    import app.core.redis as redis_mod
    app.api.routes_products.settings = TEST_SETTINGS
    product_service.settings = TEST_SETTINGS
    app.services.redis_patterns.settings = TEST_SETTINGS
    redis_mod.settings = TEST_SETTINGS
    config.settings = TEST_SETTINGS
    product_service.reset_store()

    backend = InMemoryBackend()
    FastAPICache.init(
        backend,
        prefix=TEST_SETTINGS.cache_prefix,
        key_builder=city_key_builder,
        cache_status_header="X-Cache-Status",
    )

    # Force shared redis pool to re-create on next use (picks up TEST_SETTINGS URL)
    import asyncio
    try:
        asyncio.run(redis_mod.close_redis())
    except RuntimeError:
        pass

    app_obj = create_app(use_redis=False)
    c = TestClient(app_obj, raise_server_exceptions=True)

    yield c

    config.settings = original_settings
    weather_service._reset_call_count()
    try:
        asyncio.run(redis_mod.close_redis())
    except RuntimeError:
        pass


@pytest.fixture()
async def real_redis(request):
    """Real Redis client on DB 15. Skips unless --redis is passed and Redis is up."""
    if not request.config.getoption("--redis"):
        pytest.skip("Pass --redis to run real-Redis tests (needs docker compose up -d)")
    from redis import asyncio as aioredis
    client = aioredis.from_url("redis://localhost:6379/15", decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"Redis not reachable: {exc}")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
