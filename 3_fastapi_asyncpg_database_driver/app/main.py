from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_products import router as products_router
from app.core.config import settings
from app.core.db import close_db, connect_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await connect_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Product Inventory API - Learn async database drivers with asyncpg",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(products_router)
    return app


app = create_app()