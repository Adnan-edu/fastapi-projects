from fastapi import FastAPI

from app.api.routes_users import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="FastAPI Pydantic v2 Validation",
        description="User Registration and Profile API demonstrating Pydantic v2 validation, serialization, and advanced features",
        version="0.1.0",
    )
    app.include_router(users_router)
    return app


app = create_app()