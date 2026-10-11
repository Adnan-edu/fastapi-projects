from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app_sqlmodel.core.database import get_session
from app_sqlmodel.schemas.task import TaskCreate, TaskListResponse, TaskResponse, TaskUpdate
from app_sqlmodel.services import task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task_data: TaskCreate, session: AsyncSession = Depends(get_session)):
    task = await task_service.create_task(session, task_data)
    return task


@router.get("/", response_model=TaskListResponse)
async def list_tasks(session: AsyncSession = Depends(get_session)):
    tasks = await task_service.list_tasks(session)
    return TaskListResponse(tasks=tasks, count=len(tasks))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_data: TaskUpdate, session: AsyncSession = Depends(get_session)):
    task = await task_service.update_task(session, task_id, task_data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await task_service.delete_task(session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")