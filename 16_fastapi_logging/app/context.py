"""Request-scoped logging context.

Wraps ``structlog.contextvars`` so that values bound at the start of a request
(``request_id``, ``method``, ``path``, ``user_id`` ...) are automatically merged
into every log event emitted while handling that request -- the core of
structlog's context-binding model. Because it builds on ``contextvars`` it is
safe under async and concurrent requests; each task sees its own context.
"""
import uuid  # Import uuid for generating unique request identifiers
from contextvars import ContextVar  # Import ContextVar for thread/task-local storage context

import structlog  # Import structlog for logging contextvar binding utilities

# Dedicated contextvar so we can read the current request id directly
# (e.g. to echo it back in a response header) without parsing log output.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)  # Create a request ID contextvar with a default of None


def bind_request_context(request_id: str | None = None, **fields: object) -> str:  # Define context binder function
    """Bind request-scoped fields for the current context and return the id.

    A ``request_id`` is generated when one is not supplied.
    """
    request_id = request_id or uuid.uuid4().hex  # Use supplied ID or generate a new random hex UUID string
    _request_id.set(request_id)  # Store request ID in the local ContextVar object
    structlog.contextvars.bind_contextvars(request_id=request_id, **fields)  # Bind request_id and key-value fields to structlog contextvars
    return request_id  # Return active request ID string


def get_request_id() -> str | None:  # Define request ID accessor function
    """Return the current request id, or ``None`` outside a request."""
    return _request_id.get()  # Fetch and return value currently stored in the _request_id ContextVar


def clear_request_context() -> None:  # Define request context cleanup function
    """Remove all bound context (call in a ``finally`` at end of request)."""
    _request_id.set(None)  # Reset ContextVar to store None value
    structlog.contextvars.clear_contextvars()  # Clear all key-value mappings in structlog contextvars memory

