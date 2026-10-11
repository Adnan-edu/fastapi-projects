from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.api.routes_reports import router as reports_router
from app.core.broker import broker
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(app.state, "redis", None) is None:
        app.state.redis = aioredis.Redis.from_url(
            settings.redis_url, decode_responses=True
        )

    if not broker.is_worker_process:
        await broker.startup()

    yield

    if not broker.is_worker_process:
        await broker.shutdown()

    await app.state.redis.aclose()


def create_app(redis_instance=None, start_broker=True) -> FastAPI:
    import taskiq_fastapi

    app = FastAPI(
        title="FastAPI Taskiq Background Jobs - Report Generator",
        description="Submit and track background report generation jobs using Taskiq and Redis",
        version="0.1.0",
    )

    if redis_instance is not None:
        app.state.redis = redis_instance

    app.include_router(reports_router)

    taskiq_fastapi.init(broker, "app.main:app")

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if getattr(app.state, "redis", None) is None:
            app.state.redis = aioredis.Redis.from_url(
                settings.redis_url, decode_responses=True
            )

        if start_broker and not broker.is_worker_process:
            await broker.startup()

        yield

        if start_broker and not broker.is_worker_process:
            await broker.shutdown()

        if redis_instance is None:
            await app.state.redis.aclose()

    app.router.lifespan_context = _lifespan

    return app


app = create_app()