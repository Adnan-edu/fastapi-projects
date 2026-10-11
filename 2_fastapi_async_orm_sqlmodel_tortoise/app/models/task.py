from tortoise import fields
from tortoise.models import Model


class Task(Model):
    id = fields.IntField(primary_key=True)
    title = fields.CharField(max_length=200)
    description = fields.TextField(default="")
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tasks"

    def __str__(self) -> str:
        return f"Task(id={self.id}, title={self.title!r}, status={self.status!r})"