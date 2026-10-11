from fastapi import FastAPI

from app.api.routes_analytics import router as analytics_router
from app.api.routes_cart import router as cart_router
from app.api.routes_products import router as products_router
from app.api.routes_system import router as system_router
from app.api.routes_weather import router as weather_router
from app.core.cache import lifespan_with_memory, lifespan_with_redis


def create_app(use_redis: bool = True) -> FastAPI:
    lifespan = lifespan_with_redis if use_redis else lifespan_with_memory

    app = FastAPI(
        title="FastAPI Real Redis — Product Management Learning API",
        description="Product catalogue + cart + analytics backed by real Docker Redis. "
        "Cache-aside, locks, counters, rate-limit, idempotency, pub/sub.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(products_router)
    app.include_router(cart_router)
    app.include_router(analytics_router)
    app.include_router(system_router)
    app.include_router(weather_router)  # legacy demo, kept for regression
    return app


app = create_app()
