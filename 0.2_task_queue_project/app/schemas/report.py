# =====================================================================
# app/schemas/report.py - Pydantic schemas for report endpoints
# =====================================================================

from datetime import datetime
from pydantic import BaseModel


# Request body for POST /reports/generate.
class ReportCreate(BaseModel):
    title: str                  # Human title shown in UI listings.
    report_type: str           # "pdf" | "csv" | "excel" — validated server-side against ReportType.
    user_id: int                # Owner of the resulting report.
    query_params: str | None = None  # Optional JSON-encoded filters.
    # True -> enqueue ARQ task; False -> call ReportService synchronously.
    async_mode: bool = True


# Response shape: ORM Report row serialised back to the client.
class ReportRead(BaseModel):
    id: int
    title: str
    report_type: str
    status: str
    file_path: str | None
    user_id: int
    created_at: datetime
    completed_at: datetime | None

    # Construct directly from the ORM model attributes (joined_at, etc.).
    model_config = {"from_attributes": True}
