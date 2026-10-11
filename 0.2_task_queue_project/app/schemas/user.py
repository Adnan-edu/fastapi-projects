# =====================================================================
# app/schemas/user.py - Pydantic schemas for the /users endpoints
# =====================================================================

from datetime import datetime
from pydantic import BaseModel


# Request body for POST /users/.
class UserCreate(BaseModel):
    email: str
    username: str
    full_name: str


# Response body for GET /users and GET /users/{id}.
class UserRead(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    is_active: bool
    created_at: datetime

    # Build directly from a SQLAlchemy User row.
    model_config = {"from_attributes": True}
