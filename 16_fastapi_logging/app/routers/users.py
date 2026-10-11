"""User endpoints demonstrating structlog context binding."""
import structlog  # Import structlog for structured context logging
from fastapi import APIRouter, HTTPException  # Import router module and standard exception class
from pydantic import BaseModel  # Import base model schema parser

router = APIRouter(prefix="/users", tags=["users"])  # Instantiate APIRouter with users route prefix and tag
log = structlog.get_logger("app.users")  # Retrieve a structured logger instance for users routing namespace

# Tiny in-memory user table for the demo.
_USERS = {1: "ada", 2: "linus", 3: "grace"}  # Seed dummy dictionary mapping user IDs to names


class LoginRequest(BaseModel):  # Define login schema inheriting from BaseModel
    user_id: int  # Define user_id as an integer parameter
    password: str  # Define password as a string parameter


@router.get("/{user_id}")  # Register GET endpoint handler for user retrieval
def get_user(user_id: int):  # Endpoint function receiving user_id from path
    structlog.contextvars.bind_contextvars(user_id=user_id)  # Bind the user_id to request logging contextvars
    log.info("fetch_user")  # Log initial fetch invocation carrying request context and bound user ID
    if user_id not in _USERS:  # Check if user ID does not exist in local dict database
        log.warning("user_not_found")  # Log warning message carrying request context and user_id info
        raise HTTPException(status_code=404, detail="user not found")  # Raise HTTP 404 Exception to send to client
    log.info("user_fetched")  # Log successful fetch event
    return {"user_id": user_id, "username": _USERS[user_id]}  # Return user details payload to client


@router.post("/login")  # Register POST endpoint handler for user logins
def login(body: LoginRequest):  # Endpoint function receiving LoginRequest schema parameters
    structlog.contextvars.bind_contextvars(user_id=body.user_id)  # Bind user_id to structlog request contextvars
    log.info("login_attempt")  # Log login invocation event
    if _USERS.get(body.user_id) and body.password:  # Check if user ID exists and password string is not empty
        log.info("login_succeeded")  # Log successful validation event
        return {"user_id": body.user_id, "status": "ok"}  # Return success payload response
    log.warning("login_failed")  # Log validation failure warning
    raise HTTPException(status_code=401, detail="invalid credentials")  # Raise HTTP 401 Exception for invalid login credentials

