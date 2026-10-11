# =====================================================================
# app/config.py - Centralized application configuration
# =====================================================================
# PURPOSE
# -------
# Defines all environment-driven settings (Redis, database, API host/port)
# in ONE place using Pydantic Settings. Both the FastAPI app and the ARQ
# worker import the same `settings` singleton so they stay in sync.
#
# HOW IT WORKS
# ------------
# 1. `BaseSettings` (from pydantic-settings) auto-reads values from:
#       (a) environment variables, then
#       (b) a `.env` file (if present), then
#       (c) the class-level defaults shown below.
# 2. Type hints are enforced — bad values raise a validation error at
#    import time, so misconfiguration fails fast.
# 3. The `redis_settings` property converts the four REDIS_* fields into
#    an `arq.connections.RedisSettings` object that ARQ understands.
# =====================================================================

# Import the BaseSettings class from pydantic_settings. Subclassing it
# gives us free .env loading + env-var override + type validation.
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------- REDIS CONNECTION -----------------------
    # Host where Redis is reachable. In docker-compose the Redis service
    # is named "redis", so we override this via env var REDIS_HOST=redis.
    REDIS_HOST: str = "localhost"

    # TCP port Redis listens on. Default 6379 matches the official image.
    REDIS_PORT: int = 6379

    # Optional password. `str | None` means it may be unset (None).
    REDIS_PASSWORD: str | None = None

    # Redis logical database number (0-15 by default). Useful for keeping
    # ARQ data separate from caches in shared Redis instances.
    REDIS_DB: int = 0

    # ------------------------- DATABASE -------------------------------
    # SQLAlchemy async DSN. `sqlite+aiosqlite` selects the aiosqlite
    # driver so the engine can be used inside async functions. In prod
    # you'd swap this for a postgres URL like `postgresql+asyncpg://...`.
    DATABASE_URL: str = "sqlite+aiosqlite:///./task_queue.db"

    # ------------------------- API SERVER -----------------------------
    # Bind address — 0.0.0.0 means "listen on every network interface",
    # which is required inside containers.
    API_HOST: str = "0.0.0.0"
    # External port exposed for HTTP traffic.
    API_PORT: int = 8000

    # ------------------------- DERIVED PROPERTY -----------------------
    # `@property` turns this method into a read-only attribute. It packs
    # the 4 REDIS_* fields above into the dataclass ARQ expects when
    # creating its Redis pool or starting the worker.
    @property
    def redis_settings(self):
        # Import inside the property so the dependency is only loaded
        # when needed (lazy import — avoids a hard requirement at import).
        from arq.connections import RedisSettings

        return RedisSettings(
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            password=self.REDIS_PASSWORD,
            database=self.REDIS_DB,
        )

    # Pydantic v2 model configuration. Tells BaseSettings to ALSO read
    # variables out of `.env` and use no prefix (`REDIS_HOST` literally).
    model_config = {"env_file": ".env", "env_prefix": ""}


# Module-level singleton. Importing `settings` from anywhere in the code
# returns the same fully-validated instance. Created ONCE at import time.
settings = Settings()
