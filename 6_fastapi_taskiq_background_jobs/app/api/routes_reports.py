from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from redis.asyncio import Redis

from app.services.report_service import ReportService, VALID_REPORT_TYPES, JobStatus
from app.tasks.report_tasks import generate_report, generate_report_with_retry

router = APIRouter(prefix="/reports", tags=["reports"])


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


class SubmitReportRequest(BaseModel):
    report_type: str
    retry: bool = False


class SubmitReportResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    report_type: str
    created_at: str
    started_at: str
    completed_at: str
    error: str
    result: str


@router.post("/submit", response_model=SubmitReportResponse, status_code=202)
async def submit_report(
    body: SubmitReportRequest,
    redis: Annotated[Redis, Depends(get_redis)],
):
    if body.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid report_type '{body.report_type}'. Must be one of: {sorted(VALID_REPORT_TYPES)}",
        )

    service = ReportService(redis)
    job_id = await service.create_job(body.report_type)

    task_func = generate_report_with_retry if body.retry else generate_report
    await task_func.kiq(job_id=job_id, report_type=body.report_type)

    return SubmitReportResponse(
        job_id=job_id,
        status=JobStatus.PENDING.value,
        message=f"Report job '{body.report_type}' submitted. Use GET /reports/{job_id}/status to check progress.",
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    redis: Annotated[Redis, Depends(get_redis)],
):
    service = ReportService(redis)
    data = await service.get_job_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobStatusResponse(**data)