# =====================================================================
# app/models/job_log.py - Persistent audit trail for ARQ jobs
# =====================================================================
# PURPOSE
# -------
# ARQ already stores job results in Redis, but Redis is volatile.
# `JobLog` is the long-term, queryable record of every job we enqueue:
#   - which task it ran
#   - what arguments it received
#   - whether it succeeded or failed
#   - how many retries it consumed
#   - when each phase happened (created, started, completed)
#
# The API route /jobs/enqueue inserts a row when enqueuing, and a
# cleanup cron job (cleanup_tasks.py) deletes old rows on a schedule.
# =====================================================================

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# String-backed Python Enum. Stored in DB as the lowercase string value
# (e.g. "pending") rather than the position — easier to inspect manually.
class JobStatus(str, enum.Enum):
    PENDING = "pending"      # Enqueued but not picked up yet
    RUNNING = "running"      # Worker is currently executing it
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Exhausted max_tries
    RETRYING = "retrying"    # Will be re-attempted after defer


class JobLog(Base):
    __tablename__ = "job_logs"

    # UUID4 primary key as a string. We generate it on the Python side
    # so the row has an id BEFORE the INSERT round-trip.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The opaque ID ARQ assigns when enqueueing (used to look the job up
    # in Redis later via the /jobs/{id}/status endpoint). Nullable
    # because the enqueue could fail (returns None for duplicate _job_id).
    arq_job_id: Mapped[str | None] = mapped_column(String(100), index=True)
    # The task function name (e.g. "send_welcome_email"). Indexed so
    # we can quickly filter by task type.
    task_name: Mapped[str] = mapped_column(String(100), index=True)
    # Lifecycle status. Defaults to PENDING when the row is created.
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    # JSON-ish text containing the arguments passed to the task.
    input_data: Mapped[str | None] = mapped_column(Text)
    # JSON-ish text containing the task's return value (after success).
    result_data: Mapped[str | None] = mapped_column(Text)
    # Last error message if the job failed permanently.
    error_message: Mapped[str | None] = mapped_column(Text)
    # How many attempts the worker has consumed.
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    # Phase timestamps. Created is set on INSERT; the others are updated
    # by the worker as the job progresses.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
