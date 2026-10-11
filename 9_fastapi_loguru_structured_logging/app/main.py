from fastapi import FastAPI

from app.api.routes_payments import router as payments_router
from app.core.logging import setup_logging
from app.core.middleware import request_id_middleware


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="FastAPI Loguru Structured Logging - Payment Events API",
        description="Payment Events API demonstrating production-style structured logging with Loguru",
        version="0.1.0",
    )

    @app.get("/health", tags=["health"], include_in_schema=False)
    def health():
        return {"status": "ok"}

    app.middleware("http")(request_id_middleware)
    app.include_router(payments_router)

    return app


app = create_app()