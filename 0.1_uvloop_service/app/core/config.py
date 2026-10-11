from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "uvloop_service"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_prefix = "UVLOOP_"


settings = Settings()
