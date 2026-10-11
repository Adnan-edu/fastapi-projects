import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_REPORT_TYPES = {"sales", "financial", "user_activity"}


class ReportService:
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    def _job_key(self, job_id: str) -> str:
        return f"report:job:{job_id}"

    async def create_job(self, report_type: str) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        key = self._job_key(job_id)
        await self._redis.hset(key, mapping={
            "job_id": job_id,
            "status": JobStatus.PENDING.value,
            "report_type": report_type,
            "created_at": now,
            "started_at": "",
            "completed_at": "",
            "error": "",
            "result": "",
        })
        await self._redis.expire(key, 86400)
        return job_id

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str = "",
        result: str = "",
    ) -> None:
        key = self._job_key(job_id)
        now = datetime.now(timezone.utc).isoformat()
        mapping: dict[str, str] = {"status": status.value}

        if status == JobStatus.PROCESSING:
            mapping["started_at"] = now
        elif status == JobStatus.COMPLETED:
            mapping["completed_at"] = now
            mapping["result"] = result
        elif status == JobStatus.FAILED:
            mapping["completed_at"] = now
            mapping["error"] = error

        await self._redis.hset(key, mapping=mapping)

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        key = self._job_key(job_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in data.items()}

    async def generate_report_content(self, report_type: str, simulated_delay: float = 5.0) -> str:
        import asyncio
        await asyncio.sleep(simulated_delay)

        reports: dict[str, str] = {
            "sales": f"Sales Report generated at {datetime.now(timezone.utc).isoformat()}. Total revenue: $1,234,567.",
            "financial": f"Financial Report generated at {datetime.now(timezone.utc).isoformat()}. Net profit: $567,890.",
            "user_activity": f"User Activity Report generated at {datetime.now(timezone.utc).isoformat()}. Active users: 42,000.",
        }
        return reports.get(report_type, f"Unknown Report generated at {datetime.now(timezone.utc).isoformat()}")