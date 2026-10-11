from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "fastapi-task-manager"
    db_url: str = "sqlite://db.sqlite3"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()