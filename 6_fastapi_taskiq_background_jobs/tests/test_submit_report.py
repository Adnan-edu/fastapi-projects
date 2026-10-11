import pytest

from app.services.report_service import JobStatus


class TestSubmitReport:
    def test_submit_sales_report(self, client):
        response = client.post("/reports/submit", json={"report_type": "sales"})
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert data["job_id"]
        assert "sales" in data["message"]

    def test_submit_financial_report(self, client):
        response = client.post("/reports/submit", json={"report_type": "financial"})
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert "financial" in data["message"]

    def test_submit_user_activity_report(self, client):
        response = client.post("/reports/submit", json={"report_type": "user_activity"})
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"

    def test_submit_report_with_retry(self, client):
        from app.tasks import report_tasks

        response = client.post(
            "/reports/submit", json={"report_type": "sales", "retry": True}
        )
        assert response.status_code == 202
        report_tasks.generate_report_with_retry.kiq.assert_called_once()

    def test_submit_without_retry_uses_default_task(self, client):
        from app.tasks import report_tasks

        response = client.post("/reports/submit", json={"report_type": "sales"})
        assert response.status_code == 202
        report_tasks.generate_report.kiq.assert_called_once()
        report_tasks.generate_report_with_retry.kiq.assert_not_called()

    def test_submit_invalid_report_type(self, client):
        response = client.post(
            "/reports/submit", json={"report_type": "invalid_type"}
        )
        assert response.status_code == 422
        data = response.json()
        assert "invalid" in data["detail"].lower() or "Invalid" in data["detail"]

    def test_submit_returns_unique_job_ids(self, client):
        response1 = client.post("/reports/submit", json={"report_type": "sales"})
        response2 = client.post("/reports/submit", json={"report_type": "sales"})
        assert response1.json()["job_id"] != response2.json()["job_id"]

    @pytest.mark.anyio
    async def test_submit_creates_pending_job_in_redis(self, client, service):
        response = client.post("/reports/submit", json={"report_type": "sales"})
        job_id = response.json()["job_id"]
        status = await service.get_job_status(job_id)
        assert status is not None
        assert status["status"] == JobStatus.PENDING.value
        assert status["report_type"] == "sales"