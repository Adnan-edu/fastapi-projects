# =====================================================================
# app/api/users.py - User CRUD endpoints + welcome-email enqueue
# =====================================================================
# PURPOSE
# -------
# The POST /users endpoint shows the smallest end-to-end ARQ flow:
# 1. Create a DB row
# 2. Enqueue a follow-up task (send_welcome_email)
# 3. Return immediately — the email is delivered by the worker.
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead
from app.arq_utils import get_redis_pool
# Imported for completeness even though we enqueue by string name —
# this guarantees the task module is loaded so its registration runs.
from app.tasks.email_tasks import send_welcome_email

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserRead)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Reject duplicate emails up front (the DB unique constraint would
    # also catch it, but we surface a clearer 400 here).
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Build and persist the User row.
    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Fire-and-forget welcome email. The deterministic _job_id ensures
    # re-creating the same user (e.g. retry) never queues two emails.
    redis = await get_redis_pool()
    await redis.enqueue_job("send_welcome_email", user.id, _job_id=f"welcome_email_{user.id}")

    return user


@router.get("/", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)):
    # No filtering / pagination — demo only.
    result = await db.execute(select(User))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
