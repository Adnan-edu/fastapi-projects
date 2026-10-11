from tortoise import Tortoise

Tortoise.init_models(["app.models.task"], "models")