# =====================================================================
# app/tasks/etl_tasks.py - ARQ tasks for ETL / data sync
# =====================================================================
# Pipeline tasks model the "long-running batch job" use case. They
# typically share resources (DB pools, HTTP clients) created in
# on_worker_startup and accessed via the ctx dict.
# =====================================================================

import logging
from datetime import datetime, timezone

from app.services.etl_service import ETLService
from app.tasks._retry import retry_with_backoff

logger = logging.getLogger(__name__)


async def run_data_pipeline(ctx: dict, pipeline_name: str) -> dict:
    """Run a data pipeline (ETL job).

    ARQ Feature: on_startup/on_shutdown for shared DB connections.
    The WorkerSettings uses on_startup to initialize a DB session pool
    and on_shutdown to close it. This task uses ctx['db_session'] to
    access the database during execution.
    """
    logger.info("Running data pipeline: %s", pipeline_name)
    etl_service = ctx.get("etl_service", ETLService())
    result = await etl_service.run_pipeline(pipeline_name)
    logger.info("Data pipeline %s completed: %s rows processed", pipeline_name, result.get("rows_processed", 0))
    return {"pipeline_name": pipeline_name, "status": "completed", "rows_processed": result.get("rows_processed", 0), "timestamp": datetime.now(timezone.utc).isoformat()}


async def sync_external_data(ctx: dict, source: str) -> dict:
    """Synchronize data from an external source.

    ARQ Feature: Retry with exponential backoff for flaky external APIs.
    If the external API is unavailable, raises Retry with increasing delay.
    Max retries configured in WorkerSettings.
    """
    logger.info("Syncing external data from: %s (try %s)", source, ctx["job_try"])
    etl_service = ctx.get("etl_service", ETLService())

    try:
        result = await etl_service.sync_data(source)
        logger.info("External data synced from %s: %s records", source, result.get("records_synced", 0))
        return {"source": source, "status": "completed", "records_synced": result.get("records_synced", 0), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Backoff factor 8s: try1=8, try2=16, try3=24, try4=32, try5=40.
        # Larger delays than image tasks because external APIs need more
        # breathing room to recover from rate limits.
        logger.warning("External sync failed for %s: %s (try %s)", source, e, ctx["job_try"])
        retry_with_backoff(ctx, factor=8)
