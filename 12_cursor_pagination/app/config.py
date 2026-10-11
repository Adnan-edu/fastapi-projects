from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://cursor:cursor@localhost:5432/cursor_pagination",
        alias="DATABASE_URL",
    )

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="info", alias="APP_LOG_LEVEL")

    default_page_limit: int = Field(default=50, alias="DEFAULT_PAGE_LIMIT")
    max_page_limit: int = Field(default=500, alias="MAX_PAGE_LIMIT")

    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")


@lru_cache
def get_settings() -> Settings:
    return Settings()
