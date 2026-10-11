from fastapi import APIRouter, HTTPException, status

from app.schemas.user import (
    NotificationPreference,
    UserPublicResponse,
    UserProfile,
    UserRegister,
    UserUpdate,
    user_register_adapter,
)
from app.services import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("/", response_model=UserPublicResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserRegister) -> UserPublicResponse:
    try:
        return user_service.register_user(user_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{user_id}", response_model=UserProfile)
def get_user(user_id: int) -> UserProfile:
    profile = user_service.get_user(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return profile


@router.patch("/{user_id}", response_model=UserProfile)
def update_user(user_id: int, user_data: UserUpdate) -> UserProfile:
    try:
        profile = user_service.update_user(user_id, user_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return profile


@router.get("/", response_model=list[UserPublicResponse])
def list_users() -> list[UserPublicResponse]:
    return user_service.list_users()


@router.post("/validate-notification", response_model=dict)
def validate_notification_preference(preference: NotificationPreference) -> dict:
    return {"type": preference.type, "data": preference.model_dump()}


@router.post("/validate-batch")
def validate_batch_users(raw_users: list[dict]) -> list[dict]:
    validated = user_register_adapter.validate_python(raw_users)
    return [u.model_dump() for u in validated]