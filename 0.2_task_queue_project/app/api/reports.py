# =====================================================================
# app/api/reports.py - Report generation endpoints
# =====================================================================
# PURPOSE
# -------
# Lets clients request PDF/CSV reports either:
#   - asynchronously (enqueue + immediate response with status=PENDING)
#   - synchronously  (block until the file is produced)
# Demonstrates ARQ queue routing (_queue_name) and per-type task selection.
# =====================================================================

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.arq_utils import get_redis_pool
from app.models import Report, ReportType, ReportStatus, User
from app.schemas.report import ReportCreate, ReportRead

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", response_model=ReportRead)
async def generate_report(report_in: ReportCreate, db: AsyncSession = Depends(get_db)):
    """Generate a report. Uses ARQ queue when async_mode=True.

    ARQ Features demonstrated:
    - async_mode=True: enqueue_job with _job_id for dedup
    - async_mode=False: Call service directly (sync processing)
    - Different queue routing: report tasks go to "report" queue in microservice mode
    """
    # Ensure the requesting user actually exists.
    result = await db.execute(select(User).where(User.id == report_in.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Persist the report row in PENDING state so the client can poll it.
    report = Report(
        title=report_in.title,
        # Convert the request string ("pdf") into the ReportType enum.
        report_type=ReportType(report_in.report_type),
        user_id=report_in.user_id,
        query_params=report_in.query_params,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    if report_in.async_mode:
        # ASYNC PATH: enqueue task and let the worker do the heavy lifting.
        redis = await get_redis_pool()
        if report_in.report_type == "pdf":
            # PDF report task. _job_id keyed by report id => dedup
            # against accidental double-clicks. _queue_name="report"
            # routes to WorkerSettingsReport in microservice mode.
            job = await redis.enqueue_job(
                "generate_pdf_report",
                report.id,
                _job_id=f"report_pdf_{report.id}",
                _queue_name="report",
            )
        else:
            # Default: CSV export.
            job = await redis.enqueue_job(
                "generate_csv_export",
                report.id,
                _job_id=f"report_csv_{report.id}",
                _queue_name="report",
            )
    else:
        # SYNC PATH: run the service inline. Useful for tests where we
        # don't want to spin up a worker.
        from app.services.report_service import ReportService
        report_service = ReportService()
        if report_in.report_type == "pdf":
            await report_service.generate_pdf(report.id)
        else:
            await report_service.generate_csv(report.id)
        report.status = ReportStatus.COMPLETED
        await db.commit()
        await db.refresh(report)

    return report


@router.get("/", response_model=list[ReportRead])
async def list_reports(db: AsyncSession = Depends(get_db)):
    # Newest reports first.
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
