"""POST /export — submission endpoint.

Contract: returns a UUID job_id and ``status="queued"`` immediately;
calls ``enqueue_job("run_export", job_id, filters_dict, _job_id=job_id)``
on the Arq Redis pool.
"""

from __future__ import annotations

import uuid


def test_submit_returns_uuid_job_id_and_queued_status(client):
    r = client.post("/export", json={"status": "paid", "country": "US"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    # job_id parses as a UUID
    uuid.UUID(body["job_id"])


def test_submit_enqueues_run_export_with_filters(client):
    payload = {"status": "paid", "country": "US", "customer_id": 7}
    r = client.post("/export", json=payload)
    job_id = r.json()["job_id"]

    pool = client.fake_pool
    assert len(pool.enqueued) == 1
    record = pool.enqueued[0]
    assert record["function"] == "run_export"
    # positional args: (job_id, filters_dict)
    assert record["args"][0] == job_id
    assert record["args"][1] == {
        "status": "paid",
        "country": "US",
        "customer_id": 7,
    }
    # the Arq job_id matches the one returned to the client (idempotency-friendly)
    assert record["job_id"] == job_id


def test_submit_with_no_filters_is_allowed(client):
    r = client.post("/export", json={})
    assert r.status_code == 200
    args = client.fake_pool.enqueued[0]["args"]
    assert args[1] == {"status": None, "country": None, "customer_id": None}
