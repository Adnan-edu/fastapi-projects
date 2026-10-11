"""Application settings loaded from environment / .env.

A single ``Settings`` object drives every observability decision: which renderer
the logging pipeline uses (Loguru console vs structlog JSON), whether Sentry
initializes, and where rotating log files are written.
"""
from functools import lru_cache  # Import cache decorator for process-wide settings caching
from typing import Literal  # Import Literal for configuration type constraints

from pydantic_settings import BaseSettings, SettingsConfigDict  # Import Pydantic config classes

Environment = Literal["development", "production"]  # Constrain settings to dev or prod environments


class Settings(BaseSettings):  # Define application settings schema inheriting from Pydantic BaseSettings
    """Runtime configuration, overridable via environment variables or ``.env``."""

    model_config = SettingsConfigDict(  # Define configuration parameters for Pydantic Settings
        env_file=".env",  # Specify source dot-env file to load variables from
        env_file_encoding="utf-8",  # Set file encoding to UTF-8
        case_sensitive=False,  # Allow case-insensitive matching of environment keys
        extra="ignore",  # Ignore any extra environment variables not defined in Settings
    )

    environment: Environment = "development"  # Configure environment type (defaults to development)
    log_level: str = "DEBUG"  # Set minimum logging level filter (defaults to DEBUG)
    sentry_dsn: str | None = None  # Define Sentry endpoint URL (optional, defaults to None)
    app_version: str = "0.1.0"  # Set application release identifier version
    log_dir: str = "logs"  # Specify file target output directory for Loguru rotating log files
    logfire_token: str | None = None  # Pydantic Logfire write token (optional, defaults to None; leave empty to disable)

    @property
    def is_production(self) -> bool:  # Property helper to check if env is production
        return self.environment == "production"  # Returns True if environment matches "production"


@lru_cache
def get_settings() -> Settings:  # Define settings accessor function wrapped with lru_cache
    """Return a process-wide cached ``Settings`` instance."""
    return Settings()  # Construct and return Settings instance (cached after first run)

