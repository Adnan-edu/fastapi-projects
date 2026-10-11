"""Tests for app.context request-scoped contextvar helpers."""
import structlog

from app.context import (
    bind_request_context,
    clear_request_context,
    get_request_id,
)


def setup_function():
    clear_request_context()


def teardown_function():
    clear_request_context()


def test_get_request_id_none_when_unbound():
    assert get_request_id() is None


def test_bind_sets_request_id_and_returns_it():
    rid = bind_request_context(request_id="abc-123", method="GET", path="/x")
    assert rid == "abc-123"
    assert get_request_id() == "abc-123"


def test_bind_generates_request_id_when_missing():
    rid = bind_request_context(method="GET", path="/x")
    assert isinstance(rid, str) and len(rid) > 0
    assert get_request_id() == rid


def test_bound_fields_appear_in_structlog_event():
    bind_request_context(request_id="req-9", method="POST", path="/pay")
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, cap])
    structlog.get_logger().info("hello")
    entry = cap.entries[0]
    assert entry["request_id"] == "req-9"
    assert entry["method"] == "POST"
    assert entry["path"] == "/pay"


def test_clear_removes_context():
    bind_request_context(request_id="to-clear")
    clear_request_context()
    assert get_request_id() is None
