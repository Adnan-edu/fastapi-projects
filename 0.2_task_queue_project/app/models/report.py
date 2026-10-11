# =====================================================================
# app/models/report.py - User-requested generated reports
# =====================================================================
# PURPOSE
# -------
# Holds metadata about asynchronously generated reports (PDF, CSV,
# Excel). The Report row is created with status=PENDING when the user
# hits POST /reports/generate. The worker updates status -> GENERATING
# -> COMPLETED and writes the file_path of the produced artefact.
# =====================================================================

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Supported output formats. Drives which task the API enqueues
# (generate_pdf_report vs generate_csv_export).
class ReportType(str, enum.Enum):
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"


# Lifecycle state, mirrored by the worker as it processes the report.
class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Human-readable title shown in UIs.
    title: Mapped[str] = mapped_column(String(255))
    # Output format the user requested. Stored as the enum value.
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType))
    # Workflow state — updated by the worker.
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.PENDING)
    # Where the finished artefact lives on disk / object storage.
    file_path: Mapped[str | None] = mapped_column(String(500))
    # FK to the user who owns the report.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    # Optional JSON-encoded filters the worker passes into the
    # underlying SQL/analytics query.
    query_params: Mapped[str | None] = mapped_column(Text)
    # Timestamps for created/completed phases.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # ORM back-reference, mirrors User.reports.
    user: Mapped["User"] = relationship(back_populates="reports")
