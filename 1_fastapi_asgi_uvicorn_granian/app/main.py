from fastapi import FastAPI

from app.api.v1.endpoints import health
from app.api.v1.router import router as v1_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Learn how FastAPI runs on ASGI servers (Uvicorn & Granian)",
        version="0.1.0",
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(v1_router)
    return app


app = create_app()