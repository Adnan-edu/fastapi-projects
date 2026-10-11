"""GET /export/{job_id} and /export/{job_id}/file."""

from __future__ import annotations

from tests.conftest import FakeJob, FakeJobInfo


def test_status_reports_in_progress(client):
    pool = client.fake_pool
    pool.jobs["abc"] = FakeJob(info_payload=FakeJobInfo(status="in_progress",
                                                       enqueue_time=1.0))
    r = client.get("/export/abc")
    assert r.status_code == 200
    body = r.json()
    assert body == {"job_id": "abc", "status": "in_progress", "enqueue_time": 1.0}


def test_status_falls_back_to_file_when_arq_forgot(client):
    # Arq drops job metadata after a TTL — the doc anticipates this.
    pool = client.fake_pool
    pool.jobs["done-job"] = FakeJob(info_payload=None)
    (client.export_dir / "done-job.csv").write_text("id\n1\n")

    r = client.get("/export/done-job")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == "done-job"
    assert body["status"] == "done"
    assert body["size"] > 0


def test_status_404_when_unknown_and_no_file(client):
    pool = client.fake_pool
    pool.jobs["nope"] = FakeJob(info_payload=None)
    r = client.get("/export/nope")
    assert r.status_code == 404


def test_download_returns_csv(client):
    csv_path = client.export_dir / "fileready.csv"
    csv_path.write_text("id,status\n1,paid\n")
    r = client.get("/export/fileready/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text == "id,status\n1,paid\n"


def test_download_404_when_file_missing(client):
    r = client.get("/export/missing/file")
    assert r.status_code == 404
