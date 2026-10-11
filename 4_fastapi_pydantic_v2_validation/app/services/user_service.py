from app.schemas.user import (
    Address,
    UserPublicResponse,
    UserProfile,
    UserRegister,
    UserUpdate,
)

_user_store: dict[int, dict] = {}
_next_id: int = 1


def _reset_store() -> None:
    global _next_id
    _user_store.clear()
    _next_id = 1


def register_user(data: UserRegister) -> UserPublicResponse:
    global _next_id

    for existing in _user_store.values():
        if existing["username"] == data.username:
            raise ValueError(f"Username '{data.username}' already exists")
        if existing["email"] == data.email:
            raise ValueError(f"Email '{data.email}' already exists")

    record = {
        "id": _next_id,
        "username": data.username,
        "email": data.email,
        "password_hash": f"hashed_{data.password}",
        "first_name": data.first_name,
        "last_name": data.last_name,
        "phone": None,
        "address": data.address.model_dump() if data.address else None,
    }
    _user_store[_next_id] = record
    _next_id += 1
    return UserPublicResponse.model_validate(record)


def get_user(user_id: int) -> UserProfile | None:
    record = _user_store.get(user_id)
    if record is None:
        return None
    return UserProfile.model_validate(record)


def update_user(user_id: int, data: UserUpdate) -> UserProfile | None:
    record = _user_store.get(user_id)
    if record is None:
        return None

    update_data = data.model_dump(exclude_none=True)
    if "email" in update_data:
        for uid, existing in _user_store.items():
            if uid != user_id and existing["email"] == update_data["email"]:
                raise ValueError(f"Email '{update_data['email']}' already exists")

    for key, value in update_data.items():
        if key == "address" and value is not None:
            record[key] = Address(**value).model_dump()
        else:
            record[key] = value

    return UserProfile.model_validate(record)


def list_users() -> list[UserPublicResponse]:
    return [UserPublicResponse.model_validate(r) for r in _user_store.values()]