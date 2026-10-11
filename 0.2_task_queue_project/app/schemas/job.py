# =====================================================================
# app/schemas/job.py - Pydantic schemas for the /jobs endpoints
# =====================================================================
# PURPOSE
# -------
# Defines the request/response shapes used by app/api/jobs.py. Pydantic
# schemas validate incoming JSON and serialize ORM objects on the way out.
# =====================================================================

from datetime import datetime

# BaseModel is Pydantic's root class — gives us validation, parsing,
# JSON serialisation, and OpenAPI schema generation for free.
from pydantic import BaseModel


# Request body for POST /jobs/enqueue.
class JobCreate(BaseModel):
    # The ARQ task to invoke (must be in WorkerSettings.functions).
    task_name: str
    # JSON-encoded positional args, parsed inside the route handler.
    input_data: str | None = None
    # Client-supplied ID used as `_job_id` for deduplication.
    idempotency_key: str | None = None


# Response shape for GET /jobs and GET /jobs/{id}. Mirrors JobLog ORM.
class JobRead(BaseModel):
    id: str
    arq_job_id: str | None
    task_name: str
    status: str
    input_data: str | None
    result_data: str | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    # `from_attributes=True` is the v2 equivalent of `orm_mode`. It
    # lets Pydantic build the schema from an ORM object's attributes
    # (joblog.task_name) rather than requiring a dict.
    model_config = {"from_attributes": True}


# Response for GET /jobs/{job_id}/status — represents the LIVE state of
# the job in Redis (not the database row).
class JobStatusResponse(BaseModel):
    arq_job_id: str
    status: str           # "queued" / "in_progress" / "complete" / "not_found"
    result: str | None = None  # Populated only when status == "complete"
