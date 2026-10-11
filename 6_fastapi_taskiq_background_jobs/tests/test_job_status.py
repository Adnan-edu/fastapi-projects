class TestJobStatus:
    def test_get_status_for_existing_job(self, client):
        submit = client.post("/reports/submit", json={"report_type": "sales"})
        job_id = submit.json()["job_id"]

        response = client.get(f"/reports/{job_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "pending"
        assert data["report_type"] == "sales"
        assert data["created_at"]

    def test_get_status_404_for_unknown_job(self, client):
        response = client.get("/reports/nonexistent-job-id/status")
        assert response.status_code == 404

    def test_status_response_has_all_fields(self, client):
        submit = client.post("/reports/submit", json={"report_type": "financial"})
        job_id = submit.json()["job_id"]

        response = client.get(f"/reports/{job_id}/status")
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert "report_type" in data
        assert "created_at" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "error" in data
        assert "result" in data

    def test_pending_job_has_empty_result_fields(self, client):
        submit = client.post("/reports/submit", json={"report_type": "sales"})
        job_id = submit.json()["job_id"]

        response = client.get(f"/reports/{job_id}/status")
        data = response.json()
        assert data["started_at"] == ""
        assert data["completed_at"] == ""
        assert data["error"] == ""
        assert data["result"] == ""

    def test_get_pending_status_after_submit(self, client):
        submit = client.post("/reports/submit", json={"report_type": "user_activity"})
        job_id = submit.json()["job_id"]

        status_resp = client.get(f"/reports/{job_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "pending"