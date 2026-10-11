from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://stream:stream@localhost:5433/stream_pagination",
        alias="DATABASE_URL",
    )

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8001, alias="APP_PORT")
    log_level: str = Field(default="info", alias="APP_LOG_LEVEL")

    # Streaming knobs.
    # `stream_chunk_size` is the server-side window: how many rows we pull from
    # the DB cursor per iteration before yielding them to the response stream.
    # Bigger = fewer round-trips but more memory; smaller = lower TTFB.
    stream_chunk_size: int = Field(default=1000, alias="STREAM_CHUNK_SIZE")

    # `stream_max_rows` is a hard cap per request. 0 means unbounded.
    # Useful as a safety belt for exports while you're tuning.
    stream_max_rows: int = Field(default=0, alias="STREAM_MAX_ROWS")

    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")


@lru_cache
def get_settings() -> Settings:
    return Settings()
