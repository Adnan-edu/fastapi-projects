"""System endpoints: health check and a deliberate crash for Sentry demos."""
import structlog  # Import structlog for structured context logging
from fastapi import APIRouter  # Import APIRouter class from FastAPI

router = APIRouter(tags=["system"])  # Instantiate APIRouter with 'system' tag configuration
log = structlog.get_logger("app.system")  # Retrieve structured logger instance for system namespace


@router.get("/health")  # Register GET healthcheck route mapping
def health():  # Endpoint function for healthcheck status
    log.debug("health_check")  # Log debug level healthcheck query event
    return {"status": "ok"}  # Return standard status ok dictionary response


@router.get("/boom")  # Register GET /boom endpoint mapping
def boom():  # Endpoint function to trigger simulated system crash
    """Raise an unhandled error to demonstrate automatic Sentry capture."""
    log.info("about_to_boom")  # Log info warning before raising simulated exception
    raise ValueError("intentional unhandled error for Sentry/observability demo")  # Raise standard unhandled ValueError exception

