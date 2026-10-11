from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass
class User:
    username: str
    role: str


FAKE_USERS: dict[str, User] = {
    "alice": User(username="alice", role="admin"),
    "bob": User(username="bob", role="editor"),
    "carol": User(username="carol", role="viewer"),
}


async def get_current_user(x_user: str = Header(..., alias="X-User")) -> User:
    if x_user not in FAKE_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown user: {x_user}",
        )
    return FAKE_USERS[x_user]