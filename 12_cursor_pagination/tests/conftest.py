"""Pytest fixtures: ASGI client bound to a real PostgreSQL.

These tests require the docker-compose `postgres` service to be running and
the `order_events` table to be populated (see README §2-3). They exercise the
full FastAPI app via `httpx.AsyncClient(ASGITransport(app))` — no network,
no Uvicorn, but a real async DB.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

load_dotenv()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # Import here so the env (DATABASE_URL etc.) is loaded first.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Manually trigger lifespan so the engine is initialised before requests
        # and disposed after.
        async with app.router.lifespan_context(app):
            yield ac


def pytest_collection_modifyitems(config, items):
    """Skip integration tests if no DATABASE_URL is reachable."""
    # Cheap check: if DATABASE_URL is not set, mark integration tests skipped.
    if not os.getenv("DATABASE_URL"):
        import pytest

        skip = pytest.mark.skip(reason="DATABASE_URL not set; skipping integration tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
