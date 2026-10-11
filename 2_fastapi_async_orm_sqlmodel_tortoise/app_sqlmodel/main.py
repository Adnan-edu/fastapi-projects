from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app_sqlmodel.api.routes_tasks import router as tasks_router
from app_sqlmodel.core.config import settings
from app_sqlmodel.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Task Manager API - SQLModel async alternative implementation",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(tasks_router)
    return app


app = create_app()