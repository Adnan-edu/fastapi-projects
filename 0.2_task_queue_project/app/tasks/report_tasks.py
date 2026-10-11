# =====================================================================
# app/tasks/report_tasks.py - ARQ tasks for report generation
# =====================================================================
# These tasks demonstrate TASK CHAINING: after generating a report
# they enqueue a follow-up email task with `_defer_by=N` so the email
# fires N seconds after generation completes (giving the user time to
# download the artefact first).
# =====================================================================

import logging
from datetime import datetime, timezone

from arq.connections import ArqRedis

from app.services.report_service import ReportService

logger = logging.getLogger(__name__)


async def generate_pdf_report(ctx: dict, report_id: int) -> dict:
    """Generate a PDF report.

    ARQ Feature: Long-running task with custom timeout.
    Configured in WorkerSettings as:
      func(generate_pdf_report, timeout=600)
    This allows up to 10 minutes for large report generation.
    """
    logger.info("Generating PDF report id=%s", report_id)
    report_service = ctx.get("report_service", ReportService())
    # Heavy work happens inside the service (would render PDF in prod).
    result = await report_service.generate_pdf(report_id)

    # Chain a follow-up email task. _defer_by=60 means "run 60s from now".
    redis: ArqRedis = ctx["redis"]
    report = result.get("report", {})
    user_id = report.get("user_id")
    # Only chain if we know who to email — defensive against missing data.
    if user_id:
        await redis.enqueue_job("send_report_email", user_id, report_id, _defer_by=60)

    logger.info("PDF report id=%s generated", report_id)
    return {"report_id": report_id, "status": "completed", "file_path": result.get("file_path"), "timestamp": datetime.now(timezone.utc).isoformat()}


async def generate_csv_export(ctx: dict, query_id: int) -> dict:
    """Generate a CSV export from a database query.

    ARQ Feature: Task chaining - after generating the CSV,
    this task enqueues a send_report_email task to notify the user.
    Demonstrates how one ARQ task can trigger another.
    """
    logger.info("Generating CSV export for query_id=%s", query_id)
    report_service = ctx.get("report_service", ReportService())
    result = await report_service.generate_csv(query_id)

    # Notice CSV result has user_id at the TOP level (different shape
    # than PDF) — that's why we pull it out differently here.
    redis: ArqRedis = ctx["redis"]
    user_id = result.get("user_id")
    if user_id:
        # Slightly shorter defer (30s) than PDFs — CSVs are typically smaller.
        await redis.enqueue_job("send_report_email", user_id, query_id, _defer_by=30)

    logger.info("CSV export query_id=%s generated", query_id)
    return {"query_id": query_id, "status": "completed", "file_path": result.get("file_path"), "timestamp": datetime.now(timezone.utc).isoformat()}
