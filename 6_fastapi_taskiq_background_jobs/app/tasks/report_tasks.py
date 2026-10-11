from typing import Annotated

from taskiq import TaskiqDepends

from app.core.broker import broker
from app.core.config import settings
from app.services.report_service import JobStatus, ReportService


async def get_redis(request=TaskiqDepends()):
    return request.app.state.redis


@broker.task
async def generate_report(
    job_id: str,
    report_type: str,
    redis=TaskiqDepends(get_redis),
) -> dict:
    service = ReportService(redis)
    try:
        await service.update_job_status(job_id, JobStatus.PROCESSING)
        result = await service.generate_report_content(
            report_type,
            simulated_delay=settings.report_simulated_delay,
        )
        await service.update_job_status(job_id, JobStatus.COMPLETED, result=result)
        return {"job_id": job_id, "status": "completed", "result": result}
    except Exception as exc:
        await service.update_job_status(job_id, JobStatus.FAILED, error=str(exc))
        raise


@broker.task(retry_on_error=True, max_retries=3)
async def generate_report_with_retry(
    job_id: str,
    report_type: str,
    redis=TaskiqDepends(get_redis),
) -> dict:
    service = ReportService(redis)
    try:
        await service.update_job_status(job_id, JobStatus.PROCESSING)
        result = await service.generate_report_content(
            report_type,
            simulated_delay=settings.report_simulated_delay,
        )
        await service.update_job_status(job_id, JobStatus.COMPLETED, result=result)
        return {"job_id": job_id, "status": "completed", "result": result}
    except Exception as exc:
        await service.update_job_status(job_id, JobStatus.FAILED, error=str(exc))
        raise