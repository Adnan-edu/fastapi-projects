from fastapi import FastAPI

from app.api.routes_orders import router as orders_router
from app.core.monitoring import setup_monitoring


def create_app() -> FastAPI:
    app = FastAPI(
        title="FastAPI Prometheus Monitoring - Orders API",
        description="Orders API demonstrating production monitoring with prometheus-fastapi-instrumentator",
        version="0.1.0",
    )

    @app.get("/health", tags=["health"], include_in_schema=False)
    def health():
        return {"status": "ok"}

    app.include_router(orders_router)
    setup_monitoring(app)
    return app


app = create_app()
