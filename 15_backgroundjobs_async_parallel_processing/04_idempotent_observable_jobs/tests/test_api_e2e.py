"""End-to-end tests against the live API + Arq worker + Postgres."""

from __future__ import annotations

from pathlib import Path

from app.ids import idempotency_key
from tests.conftest import wait_for_done


# Cheap filter that returns a small slice — keeps each test fast.
SMALL_FILTERS = {"status": "paid", "country": "US", "customer_id": 12345}


def test_post_export_enqueues(client, export_dir):
    """Test 3 — first POST returns status='queued' with a stable key."""

    r = client.post("/export", json=SMALL_FILTERS)
    assert r.status_code == 200, r.text
    body = r.json()
    expected_key = idempotency_key(SMALL_FILTERS)
    assert body["key"] == expected_key
    assert body["status"] == "queued"
    # And it eventually finishes:
    wait_for_done(client, body["key"])


def test_post_export_cached_hit(client, export_dir):
    """Test 4 — second identical POST is a cache hit, not a fresh job."""

    filters = {"status": "paid", "country": "GB"}
    r1 = client.post("/export", json=filters)
    assert r1.status_code == 200
    wait_for_done(client, r1.json()["key"])

    r2 = client.post("/export", json=filters)
    body = r2.json()
    assert body["status"] == "done"
    assert body["cached"] is True


def test_status_endpoint_progresses(client, export_dir):
    """Test 5 — GET /export/{key} reaches 'done' for a known submission."""

    filters = {"status": "failed", "country": "DE"}
    r = client.post("/export", json=filters)
    key = r.json()["key"]
    final = wait_for_done(client, key)
    assert final["status"] == "done"
    assert "size" in final and final["size"] > 0


def test_download_file_endpoint(client, export_dir):
    """Test 6 — GET /export/{key}/file returns CSV with header + body."""

    filters = {"status": "paid", "country": "CA"}
    r = client.post("/export", json=filters)
    key = r.json()["key"]
    wait_for_done(client, key)

    f = client.get(f"/export/{key}/file")
    assert f.status_code == 200
    assert f.headers["content-type"].startswith("text/csv")
    text = f.text
    assert text.startswith("id,order_id,customer_id,")
    # Header + at least one data row.
    assert len(text.splitlines()) >= 2


def test_atomic_rename_no_partial(client, export_dir: Path):
    """Test 7 — after success, no .partial scraps remain on disk."""

    filters = {"status": "paid", "country": "FR"}
    r = client.post("/export", json=filters)
    key = r.json()["key"]
    wait_for_done(client, key)

    leftovers = list(export_dir.glob("*.partial"))
    assert leftovers == [], f"unexpected partial files: {leftovers}"
    assert (export_dir / f"{key}.csv").exists()


def test_metrics_endpoint_exposes_counters(client, export_dir):
    """Test 8 — /metrics exposes all four prometheus metric families."""

    # Make sure at least one job has run so counters have non-zero data.
    filters = {"status": "paid", "country": "AU"}
    r = client.post("/export", json=filters)
    wait_for_done(client, r.json()["key"])

    m = client.get("/metrics")
    assert m.status_code == 200
    body = m.text
    # Metric names appear in HELP/TYPE lines even if a series has 0 obs.
    for needle in (
        "export_jobs_started_total",
        "export_jobs_completed_total",
        "export_job_duration_seconds",
        "export_queue_depth",
    ):
        assert needle in body, f"missing metric: {needle}"


def test_unknown_key_returns_404(client):
    """Test 9 — status and download endpoints 404 on unknown keys."""

    bogus = "0" * 16
    assert client.get(f"/export/{bogus}").status_code == 404
    assert client.get(f"/export/{bogus}/file").status_code == 404
