from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "fastapi-asgi-demo"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    workers: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()