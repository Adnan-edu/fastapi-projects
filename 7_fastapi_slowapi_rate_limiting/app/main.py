from fastapi import FastAPI

from app.api.routes_quotes import router as quotes_router
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def create_app() -> FastAPI:
    app = FastAPI(
        title="FastAPI Slowapi Rate Limiting - Public Quotes API",
        description="Public Quotes API demonstrating API rate limiting with Slowapi",
        version="0.1.0",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(quotes_router)
    return app


app = create_app()