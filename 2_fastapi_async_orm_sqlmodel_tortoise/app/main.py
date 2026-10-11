from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_tasks import router as tasks_router
from app.core.config import settings
from app.core.database import register_orm
from tortoise.contrib.fastapi import tortoise_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with register_orm(app):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Task Manager API - Learn async ORM patterns with Tortoise ORM",
        version="0.1.0",
        lifespan=lifespan,
        exception_handlers=tortoise_exception_handlers(),
    )
    app.include_router(tasks_router)
    return app


app = create_app()