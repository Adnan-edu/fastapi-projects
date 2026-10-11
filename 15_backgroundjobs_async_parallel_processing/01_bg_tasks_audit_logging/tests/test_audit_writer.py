"""Direct unit tests for the audit-log writer function."""

from __future__ import annotations

from datetime import datetime

from app import audit


def test_write_audit_log_appends_single_line(tmp_path, monkeypatch):
    target = tmp_path / "audit.log"
    monkeypatch.setattr(audit, "AUDIT_FILE", target)

    audit.write_audit_log(user_id=1, path="/orders", query={"limit": 10})

    text = target.read_text()
    assert text.endswith("\n")
    assert text.count("\n") == 1
    assert "user=1" in text
    assert "path=/orders" in text
    assert "query={'limit': 10}" in text


def test_write_audit_log_appends_without_clobbering(tmp_path, monkeypatch):
    target = tmp_path / "audit.log"
    target.write_text("preexisting line\n")
    monkeypatch.setattr(audit, "AUDIT_FILE", target)

    audit.write_audit_log(user_id=2, path="/orders", query={})

    lines = target.read_text().splitlines()
    assert lines[0] == "preexisting line"
    assert "user=2" in lines[1]


def test_write_audit_log_timestamp_is_iso_utc(tmp_path, monkeypatch):
    target = tmp_path / "audit.log"
    monkeypatch.setattr(audit, "AUDIT_FILE", target)

    audit.write_audit_log(user_id=3, path="/orders", query={})

    ts = target.read_text().split("\t", 1)[0]
    # Parses as ISO-8601 and carries timezone info (UTC offset).
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0
