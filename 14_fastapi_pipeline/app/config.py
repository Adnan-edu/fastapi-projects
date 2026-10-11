"""Application settings.

Why pydantic-settings?
----------------------
Three properties we want from a settings layer:

1. **Single source of truth.** Defaults live in code; environment overrides
   come from `.env` (in dev) or real env vars (in prod). No two files to
   keep in sync.

2. **Typed, validated.** `app_port: int = …` means a non-numeric value in
   `.env` fails fast at import time, not at the first request that tries to
   `int(os.environ["APP_PORT"])`.

3. **Cached.** Settings are read once and reused. `@lru_cache` on
   `get_settings()` gives us that with one decorator and no global state to
   manage by hand.

The `alias=` on each `Field` lets the env var name (UPPER_SNAKE) differ from
the Python attribute name (lower_snake) — that's the convention .env files
follow.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `extra="ignore"` so adding a new env var (e.g. for a future feature
    # flag) doesn't crash the app until the field is declared.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://stream:stream@localhost:5433/stream_pagination",
        alias="DATABASE_URL",
    )

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    # Port 8002 is deliberately different from 13_fastapi_streaming's 8001
    # so both apps can run side by side during a demo / comparison.
    app_port: int = Field(default=8002, alias="APP_PORT")
    log_level: str = Field(default="info", alias="APP_LOG_LEVEL")

    # Pipeline knobs. `chunk_size` is the DB pull-window: bigger = fewer
    # round-trips but more memory; smaller = lower TTFB. `max_rows=0` means
    # unbounded (no hard cap).
    pipeline_chunk_size: int = Field(default=1000, alias="PIPELINE_CHUNK_SIZE")
    pipeline_max_rows: int = Field(default=0, alias="PIPELINE_MAX_ROWS")

    # DB pool sizing. Streaming endpoints can hold a session per chunk, but
    # because we use short sessions the *concurrent* checkout count is what
    # matters here, not the response duration. 10 base + 20 overflow handles
    # a reasonable demo load.
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    `lru_cache` with no arguments memoizes on the (empty) arg tuple, so this
    is effectively a thread-safe lazy singleton. First call builds and
    validates the Settings; subsequent calls are a dict lookup.
    """
    return Settings()
