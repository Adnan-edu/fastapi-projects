"""Main application entry point.

Wired with FastAPI, configuration settings, logging configuration, Sentry setup,
custom request context middleware, routers, and a global exception handler.
"""
import sentry_sdk  # Import Sentry SDK for error monitoring
import structlog  # Import Structlog for structured logging
from fastapi import FastAPI, Request  # Import FastAPI framework classes and HTTP Request representation
from fastapi.responses import JSONResponse  # Import standard JSON response structure

from app.config import Settings, get_settings  # Import configuration schemas and loader
from app.logfire_setup import init_logfire  # Import Logfire initialization wrapper
from app.logging_config import configure_logging  # Import function to bootstrap custom logging pipeline
from app.middleware import RequestContextMiddleware  # Import request context tracing middleware
from app.routers import payments, system, users  # Import endpoint routers
from app.sentry_setup import init_sentry  # Import Sentry initialization wrapper

log = structlog.get_logger(__name__)  # Retrieve a structured logger instance for this module


def create_app(settings: Settings | None = None) -> FastAPI:  # Define the app factory function
    """Create and configure a FastAPI application instance."""
    if settings is None:  # Check if custom settings are not passed (runtime startup)
        settings = get_settings()  # Load cached configuration settings from environment / .env

    configure_logging(settings)  # Configure the unified Loguru / Structlog logging pipeline
    init_sentry(settings)  # Initialize Sentry if a DSN is configured

    app = FastAPI(  # Instantiate FastAPI application
        title="FastAPI Observability Stack Demo",  # Set application title
        description="Demo application showcasing Loguru, Structlog, and Sentry integration.",  # Set description
        version=settings.app_version,  # Set API version from settings
    )

    app.add_middleware(RequestContextMiddleware)  # Add middleware to trace request duration and bind context vars

    app.include_router(system.router)  # Attach endpoints for health checks and deliberate exceptions
    app.include_router(users.router)  # Attach endpoints for user logins and profiles
    app.include_router(payments.router)  # Attach endpoints for gateway charge transactions

    init_logfire(settings, app)  # Initialize Logfire tracing and instrument FastAPI app

    @app.exception_handler(Exception)  # Decorator to catch all unhandled exceptions globally
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # Exception handler function
        log.exception("unhandled_error", error=str(exc))  # Log exception with traceback, level=ERROR, plus bound context vars

        sentry_sdk.capture_exception(exc)  # Capture and upload the unhandled exception details to Sentry

        return JSONResponse(  # Return clean sanitized JSON response to client
            status_code=500,  # Set HTTP status code to 500 (Internal Server Error)
            content={"detail": "Internal Server Error"},  # Omit trace information from the response body for security
        )

    log.info("app_created", version=settings.app_version, environment=settings.environment)  # Log successful app factory execution
    return app  # Return fully configured FastAPI application instance


app = create_app()  # Run the factory to instantiate global 'app' object for Uvicorn imports

