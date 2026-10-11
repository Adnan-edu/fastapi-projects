from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    rate_limit_default: str = "10/minute"
    rate_limit_storage_uri: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()