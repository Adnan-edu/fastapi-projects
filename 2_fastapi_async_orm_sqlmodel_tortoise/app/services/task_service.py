from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


async def create_task(task_data: TaskCreate) -> Task:
    task = await Task.create(**task_data.model_dump())
    return task


async def list_tasks() -> list[Task]:
    return await Task.all().order_by("-created_at")


async def get_task(task_id: int) -> Task | None:
    return await Task.get_or_none(id=task_id)


async def update_task(task_id: int, task_data: TaskUpdate) -> Task | None:
    task = await Task.get_or_none(id=task_id)
    if not task:
        return None
    update_data = task_data.model_dump(exclude_unset=True) # model_dump(exclude_unset=True) ensures partial updates only send changed fields
    if update_data:
        await task.update_from_dict(update_data).save()
    return task


async def delete_task(task_id: int) -> bool:
    deleted_count = await Task.filter(id=task_id).delete()
    return deleted_count > 0