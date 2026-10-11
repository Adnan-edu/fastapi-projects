from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings


def get_api_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return f"key:{api_key}"
    return f"ip:{get_remote_address(request)}"


PLAN_LIMITS = {
    "admin": "1000/minute",
    "pro": "20/minute",
    "free": "3/minute",
}


def get_plan_from_key(api_key: str) -> str:
    if api_key.startswith("admin_"):
        return "admin"
    if api_key.startswith("pro_"):
        return "pro"
    return "free"


def dynamic_plan_limit(key: str) -> str:
    if key.startswith("key:"):
        api_key = key[4:]
    else:
        api_key = ""
    plan = get_plan_from_key(api_key)
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": str(exc.detail),
        },
    )


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
)