"""Sentry initialization with a graceful no-op fallback.

When ``SENTRY_DSN`` is set, Sentry is initialized with the FastAPI integration so
every unhandled exception is captured automatically with request context. When
the DSN is absent, initialization is skipped cleanly and the application runs
normally -- handy for local development, tests, and CI where there is no DSN.
"""
import sentry_sdk  # Import Sentry SDK for error monitoring and tracing
import structlog  # Import Structlog for structured logging
from sentry_sdk.integrations.fastapi import FastApiIntegration  # Import FastAPI integration for Sentry
from sentry_sdk.integrations.starlette import StarletteIntegration  # Import Starlette integration for Sentry

from app.config import Settings  # Import application Settings class

log = structlog.get_logger(__name__)  # Retrieve a structured logger instance for this module


def init_sentry(settings: Settings) -> bool:  # Define Sentry initialization function accepting settings
    """Initialize Sentry if a DSN is configured.

    Returns ``True`` when Sentry was initialized, ``False`` when skipped.
    """
    if not settings.sentry_dsn:  # Check if Sentry DSN is not configured/empty
        log.info("sentry_disabled", reason="no SENTRY_DSN configured")  # Log info message explaining Sentry is disabled
        return False  # Return False to signify Sentry was not initialized

    sentry_sdk.init(  # Initialize Sentry SDK with configurations
        dsn=settings.sentry_dsn,  # Set the Sentry Data Source Name (DSN) destination URL
        integrations=[  # Provide integration wrappers
            StarletteIntegration(transaction_style="endpoint"),  # Enable Starlette route profiling by endpoint name
            FastApiIntegration(transaction_style="endpoint"),  # Enable FastAPI request context tracking by endpoint name
        ],
        traces_sample_rate=0.2,  # Sample 20% of transactions for performance tracing
        profiles_sample_rate=0.1,  # Sample 10% of traced transactions for CPU profiling
        environment=settings.environment,  # Tag reported events with environment name (e.g. production)
        release=settings.app_version,  # Tag reported events with release version number
    )
    log.info("sentry_enabled", environment=settings.environment, release=settings.app_version)  # Log successful initialization
    return True  # Return True to indicate Sentry has been configured

