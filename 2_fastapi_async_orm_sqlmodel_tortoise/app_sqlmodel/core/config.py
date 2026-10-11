from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "fastapi-task-manager-sqlmodel"
    db_url: str = "sqlite+aiosqlite:///db_sqlmodel.sqlite3"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()