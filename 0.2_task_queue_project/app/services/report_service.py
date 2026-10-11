# =====================================================================
# app/services/report_service.py - Report generation stub
# =====================================================================
# Production would render PDFs with WeasyPrint / ReportLab and write
# CSVs to S3. This stub returns plausible-looking file paths plus a
# nested `report` dict containing the user_id used to chain a follow-up
# email task in app/tasks/report_tasks.py.
# =====================================================================

import logging
import uuid

logger = logging.getLogger(__name__)


class ReportService:
    """Service for report generation. Used by both sync API and async ARQ tasks."""

    # PDF path: returns `report.user_id` so the calling task can chain
    # an email to that user via redis.enqueue_job("send_report_email", ...).
    async def generate_pdf(self, report_id: int) -> dict:
        logger.info("Generating PDF for report_id=%s", report_id)
        file_path = f"/reports/{uuid.uuid4().hex[:8]}_report_{report_id}.pdf"
        return {"file_path": file_path, "report_id": report_id, "report": {"user_id": 1, "title": f"Report {report_id}"}}

    # CSV path: returns `user_id` directly at the top level (different
    # shape than PDF — matches what generate_csv_export task expects).
    async def generate_csv(self, query_id: int) -> dict:
        logger.info("Generating CSV for query_id=%s", query_id)
        file_path = f"/exports/{uuid.uuid4().hex[:8]}_export_{query_id}.csv"
        return {"file_path": file_path, "query_id": query_id, "user_id": 1}
