from functools import partial
from pathlib import Path

from tortoise.config import AppConfig, DBUrlConfig, TortoiseConfig
from tortoise.contrib.fastapi import RegisterTortoise

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent

TORTOISE_ORM = TortoiseConfig(
    connections={"default": DBUrlConfig(url=settings.db_url)},
    apps={
        "models": AppConfig(
            models=["app.models"],
            default_connection="default",
        ),
    },
)

register_orm = partial(
    RegisterTortoise,
    config=TORTOISE_ORM,
    generate_schemas=True,
)