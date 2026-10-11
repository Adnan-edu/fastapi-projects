from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "fastapi-product-inventory"
    database_url: str = "postgres://productuser:productpass@localhost:5432/productdb"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()