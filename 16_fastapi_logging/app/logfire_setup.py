"""Pydantic Logfire initialization with a graceful no-op fallback.

When ``LOGFIRE_TOKEN`` is set, Logfire is configured and the FastAPI application
is instrumented for automatic request/response tracing, argument capture, and
live log forwarding to the Logfire web console.  When the token is absent,
initialization is skipped cleanly and the application runs normally.
"""
import logfire  # Import Pydantic Logfire SDK for observability and tracing
import structlog  # Import structlog for structured logging

from app.config import Settings  # Import application Settings class

log = structlog.get_logger(__name__)  # Retrieve a structured logger instance for this module


def init_logfire(settings: Settings, app=None) -> bool:  # Define Logfire initialization function
    """Configure Logfire and instrument the FastAPI app if a token is present.

    Returns ``True`` when Logfire was initialized, ``False`` when skipped.
    """
    if not settings.logfire_token:  # Check if Logfire token is not configured/empty
        log.info("logfire_disabled", reason="no LOGFIRE_TOKEN configured")  # Log info that Logfire is disabled
        return False  # Return False to signify Logfire was not initialized

    logfire.configure(  # Initialize Logfire SDK with configurations
        token=settings.logfire_token,  # Set the Logfire write token for authentication
        service_name="fastapi-logging-demo",  # Identify this service in the Logfire dashboard
        service_version=settings.app_version,  # Tag traces with the application release version
        environment=settings.environment,  # Tag traces with the current environment name
    )

    if app is not None:  # Check if a FastAPI app instance was provided for instrumentation
        logfire.instrument_fastapi(app)  # Instrument the FastAPI app for automatic request tracing

    log.info(  # Log successful Logfire initialization
        "logfire_enabled",
        environment=settings.environment,
        version=settings.app_version,
    )
    return True  # Return True to indicate Logfire has been configured
