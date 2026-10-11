import asyncio

import pytest

from app.services.report_service import JobStatus


class TestConcurrentSubmissions:
    def test_multiple_jobs_have_distinct_ids(self, client):
        ids = set()
        for report_type in ["sales", "financial", "user_activity"]:
            response = client.post("/reports/submit", json={"report_type": report_type})
            ids.add(response.json()["job_id"])
        assert len(ids) == 3

    def test_each_job_tracks_own_report_type(self, client):
        job_ids = {}
        for rt in ["sales", "financial"]:
            resp = client.post("/reports/submit", json={"report_type": rt})
            job_ids[rt] = resp.json()["job_id"]

        for rt, jid in job_ids.items():
            status = client.get(f"/reports/{jid}/status")
            assert status.json()["report_type"] == rt


class TestInvalidInput:
    def test_empty_report_type(self, client):
        response = client.post("/reports/submit", json={"report_type": ""})
        assert response.status_code == 422

    def test_unknown_report_type(self, client):
        response = client.post("/reports/submit", json={"report_type": "inventory"})
        assert response.status_code == 422

    def test_missing_report_type_field(self, client):
        response = client.post("/reports/submit", json={})
        assert response.status_code == 422

    def test_job_id_with_special_characters_returns_404(self, client):
        response = client.get("/reports/nonexistent!@#$/status")
        assert response.status_code == 404 or response.status_code == 422

    def test_very_long_job_id_returns_404(self, client):
        fake_id = "a" * 10000
        response = client.get(f"/reports/{fake_id}/status")
        assert response.status_code == 404


class TestJobLifecycle:
    @pytest.mark.anyio
    async def test_service_create_sets_pending(self, service):
        job_id = await service.create_job("sales")
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.PENDING.value
        assert status["report_type"] == "sales"
        assert status["created_at"] != ""

    @pytest.mark.anyio
    async def test_service_update_to_processing(self, service):
        job_id = await service.create_job("financial")
        await service.update_job_status(job_id, JobStatus.PROCESSING)
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.PROCESSING.value
        assert status["started_at"] != ""

    @pytest.mark.anyio
    async def test_service_update_to_completed(self, service):
        job_id = await service.create_job("sales")
        await service.update_job_status(job_id, JobStatus.PROCESSING)
        await service.update_job_status(
            job_id, JobStatus.COMPLETED, result="Report data here"
        )
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.COMPLETED.value
        assert status["result"] == "Report data here"
        assert status["completed_at"] != ""

    @pytest.mark.anyio
    async def test_service_update_to_failed(self, service):
        job_id = await service.create_job("user_activity")
        await service.update_job_status(job_id, JobStatus.PROCESSING)
        await service.update_job_status(
            job_id, JobStatus.FAILED, error="Something went wrong"
        )
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.FAILED.value
        assert status["error"] == "Something went wrong"
        assert status["completed_at"] != ""

    @pytest.mark.anyio
    async def test_service_unknown_job_returns_none(self, service):
        status = await service.get_job_status("nonexistent-id")
        assert status is None

    @pytest.mark.anyio
    async def test_service_generate_report_content_sales(self, service):
        result = await service.generate_report_content("sales", simulated_delay=0)
        assert "Sales Report" in result
        assert "$1,234,567" in result

    @pytest.mark.anyio
    async def test_service_generate_report_content_financial(self, service):
        result = await service.generate_report_content("financial", simulated_delay=0)
        assert "Financial Report" in result
        assert "$567,890" in result

    @pytest.mark.anyio
    async def test_service_generate_report_content_user_activity(self, service):
        result = await service.generate_report_content("user_activity", simulated_delay=0)
        assert "User Activity Report" in result
        assert "42,000" in result

    @pytest.mark.anyio
    async def test_job_key_has_ttl(self, service):
        job_id = await service.create_job("sales")
        key = service._job_key(job_id)
        ttl = await service._redis.ttl(key)
        assert ttl > 0

    @pytest.mark.anyio
    async def test_full_lifecycle_pending_to_completed(self, service):
        job_id = await service.create_job("sales")

        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.PENDING.value
        assert status["started_at"] == ""

        await service.update_job_status(job_id, JobStatus.PROCESSING)
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.PROCESSING.value
        assert status["started_at"] != ""

        await service.update_job_status(
            job_id, JobStatus.COMPLETED, result="Final report content"
        )
        status = await service.get_job_status(job_id)
        assert status["status"] == JobStatus.COMPLETED.value
        assert status["result"] == "Final report content"
        assert status["completed_at"] != ""