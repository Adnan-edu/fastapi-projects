# =====================================================================
# tests/conftest.py - Shared pytest fixtures
# =====================================================================
# pytest auto-discovers this file at the start of every test run and
# makes the fixtures defined here available to ALL tests in the suite,
# no explicit import required. The fixtures cover:
#   - a test-only SQLAlchemy engine + sessionmaker (separate file DB)
#   - automatic per-test schema setup/teardown (setup_db)
#   - an httpx AsyncClient wired to our FastAPI app (client)
#   - a mocked ArqRedis pool so we never touch a real Redis (mock_redis)
#   - a context-manager that patches arq_utils to use the mock (mock_arq_pool)
#   - a helper to build a MagicMock Job (make_mock_job)
# =====================================================================

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
# pytest-asyncio's async-aware fixture decorator (handles awaitables).
import pytest_asyncio
# ASGITransport lets httpx call the FastAPI app in-process — no real
# network listening required, so tests run fast and deterministic.
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Reuse the production Base so the schema we create in tests matches prod.
from app.database import Base
# Import the FastAPI app to mount it on the transport.
from app.main import app

# Dedicated SQLite file for tests — kept out of the dev DB so a wiped
# schema between tests can't damage the dev data.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_task_queue.db"

# Build a parallel engine/session pair just for tests.
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestAsyncSession = async_sessionmaker(test_engine, expire_on_commit=False)


# Override pytest-asyncio's default per-test loop with a single
# session-scoped loop. Needed because some fixtures hold async resources
# across test cases.
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# autouse=True => runs for every test automatically.
# - Before yield: CREATE TABLE on a clean DB.
# - After yield:  DROP TABLE so the next test starts clean.
@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Hands tests a ready-to-use AsyncSession against the test DB.
@pytest_asyncio.fixture
async def db_session():
    async with TestAsyncSession() as session:
        yield session


# An httpx AsyncClient bound directly to the FastAPI ASGI app — no
# network. Base URL is fictional because we never actually dial out.
@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# A mock ArqRedis-like object. We stub the two methods our code uses
# (enqueue_job, close). Tests pass this in via ctx to verify enqueueing
# behaviour without a real Redis.
@pytest_asyncio.fixture
def mock_redis():
    redis = AsyncMock()
    redis.enqueue_job = AsyncMock()
    redis.close = AsyncMock()
    return redis


# Monkeypatches the singleton in app/arq_utils.py so any code that
# calls get_redis_pool() (e.g. an API route) receives our mock instead.
@pytest_asyncio.fixture
def mock_arq_pool(mock_redis):
    with patch("app.arq_utils.get_redis_pool", return_value=mock_redis):
        with patch("app.arq_utils._redis_pool", mock_redis):
            yield mock_redis


# Quick factory for building a Job-shaped MagicMock with a settable id.
def make_mock_job(job_id="test-job-123"):
    job = MagicMock()
    job.job_id = job_id
    return job
