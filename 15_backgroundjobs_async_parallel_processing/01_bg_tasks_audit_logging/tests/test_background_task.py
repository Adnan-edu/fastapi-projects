"""End-to-end check that hitting /orders triggers the audit write."""

from __future__ import annotations


def test_request_triggers_audit_write(client):
    assert not client.audit_file.exists()

    r = client.get("/orders?status=paid&limit=5")
    assert r.status_code == 200

    # TestClient blocks until BackgroundTasks complete, so the file
    # must exist by the time the call returns.
    assert client.audit_file.exists()
    line = client.audit_file.read_text().strip()
    assert "path=/orders" in line
    assert "'status': 'paid'" in line
    assert "'limit': 5" in line


def test_multiple_requests_append_multiple_lines(client):
    for i in range(3):
        client.get(f"/orders?limit={i + 1}")

    lines = client.audit_file.read_text().splitlines()
    assert len(lines) == 3
    assert "'limit': 1" in lines[0]
    assert "'limit': 2" in lines[1]
    assert "'limit': 3" in lines[2]
