from pathlib import Path

import casbin
from fastapi import Depends, HTTPException, status

from app.core.auth import User, get_current_user

_POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
_MODEL_PATH = _POLICIES_DIR / "model.conf"
_POLICY_PATH = _POLICIES_DIR / "policy.csv"

_enforcer: casbin.Enforcer | None = None


def get_enforcer() -> casbin.Enforcer:
    global _enforcer
    if _enforcer is None:
        _enforcer = casbin.Enforcer(str(_MODEL_PATH), str(_POLICY_PATH))
    return _enforcer


def require_permission(obj: str, act: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        enforcer = get_enforcer()
        if not enforcer.enforce(user.role, obj, act):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User '{user.username}' with role '{user.role}' "
                f"cannot {act} {obj}",
            )
        return user

    return _check