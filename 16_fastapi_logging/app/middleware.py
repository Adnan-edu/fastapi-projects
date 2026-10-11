"""Request-context logging middleware.

For every request it mints a ``request_id``, binds it (plus method and path) to
the logging context so all downstream events carry that context, logs
``request_started`` / ``request_completed`` with timing, echoes the id back in
the ``X-Request-ID`` response header, and always clears the context afterwards.
"""
import time  # Import time for high-resolution request timing

import structlog  # Import structlog for structured context logging
from starlette.middleware.base import BaseHTTPMiddleware  # Import standard Starlette HTTP middleware parent class
from starlette.requests import Request  # Import Request representation class
from starlette.responses import Response  # Import Response representation class

from app.context import bind_request_context, clear_request_context, get_request_id  # Import request contextvar utility functions

log = structlog.get_logger("app.request")  # Instantiate standard request logging namespace


class RequestContextMiddleware(BaseHTTPMiddleware):  # Define RequestContextMiddleware inheriting from BaseHTTPMiddleware
    async def dispatch(self, request: Request, call_next) -> Response:  # Core middleware hook intercepting requests
        incoming = request.headers.get("X-Request-ID")  # Read inbound X-Request-ID header to support upstream tracking
        request_id = bind_request_context(  # Initialize contextvars with request meta details
            request_id=incoming,  # Pass incoming request ID (or trigger automatic generation)
            method=request.method,  # Bind the HTTP request method (e.g. GET, POST)
            path=request.url.path,  # Bind the targeted API path context
        )
        log.info("request_started")  # Emit a request started log carrying request_id, method, path
        start = time.perf_counter()  # Record high-resolution request start timestamp
        try:  # Attempt execution of downstream routers/handlers
            response = await call_next(request)  # Propagate execution down to the next handler/middleware
        except Exception:  # Intercept unhandled handler crashes
            duration_ms = round((time.perf_counter() - start) * 1000, 2)  # Calculate elapsed duration in milliseconds
            log.exception("request_failed", duration_ms=duration_ms)  # Log failure with level=ERROR and traceback context
            raise  # Re-raise the exception to trigger global exception handlers
        else:  # On successful request processing
            duration_ms = round((time.perf_counter() - start) * 1000, 2)  # Calculate elapsed duration in milliseconds
            log.info(  # Log transaction completion event
                "request_completed",  # Log event key
                status_code=response.status_code,  # Append HTTP status code context
                duration_ms=duration_ms,  # Append response latency context
            )
            response.headers["X-Request-ID"] = get_request_id() or request_id  # Inject request ID into outgoing response headers
            return response  # Return response structure to client
        finally:  # Execution safety cleanup block
            clear_request_context()  # Discard all context variables to prevent bleedover into subsequent threads/coroutinues

