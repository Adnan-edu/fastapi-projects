from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_sqlmodel.models.task import Task
from app_sqlmodel.schemas.task import TaskCreate, TaskUpdate


async def create_task(session: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(session: AsyncSession) -> list[Task]:
    result = await session.execute(select(Task).order_by(Task.created_at.desc()))
    return list(result.scalars().all())


async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def update_task(session: AsyncSession, task_id: int, task_data: TaskUpdate) -> Task | None:
    task = await session.get(Task, task_id)
    if not task:
        return None
    update_data = task_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)
    await session.commit()
    await session.refresh(task)
    return task


async def delete_task(session: AsyncSession, task_id: int) -> bool:
    task = await session.get(Task, task_id)
    if not task:
        return False
    await session.delete(task)
    await session.commit()
    return True