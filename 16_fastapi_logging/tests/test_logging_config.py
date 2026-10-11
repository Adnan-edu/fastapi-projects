"""Tests for the env-switched logging pipeline (app.logging_config)."""
import json
import logging

import structlog

from app.config import Settings
from app.context import bind_request_context, clear_request_context
from app.logging_config import configure_logging


def setup_function():
    clear_request_context()


def teardown_function():
    clear_request_context()
    structlog.reset_defaults()


def test_production_emits_single_parseable_json_line(capsys):
    configure_logging(Settings(_env_file=None, environment="production", log_level="DEBUG"))
    bind_request_context(request_id="req-json", user_id=7)

    structlog.get_logger("svc").info("request_started", endpoint="/api/users")

    out = capsys.readouterr().out.strip()
    assert out, "expected JSON on stdout"
    line = out.splitlines()[-1]
    payload = json.loads(line)  # raises if not valid JSON
    assert payload["event"] == "request_started"
    assert payload["request_id"] == "req-json"
    assert payload["user_id"] == 7
    assert payload["endpoint"] == "/api/users"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_development_routes_through_loguru_sink(tmp_path):
    from loguru import logger as loguru_logger

    configure_logging(
        Settings(_env_file=None, environment="development", log_level="DEBUG", log_dir=str(tmp_path))
    )
    captured = []
    loguru_logger.add(captured.append, level="DEBUG")

    bind_request_context(request_id="req-dev")
    structlog.get_logger("svc").info("hello dev", foo="bar")

    messages = [m for m in captured if "hello dev" in str(m)]
    assert messages, "loguru sink did not receive the structlog event"
    extra = messages[-1].record["extra"]
    assert "req-dev" in extra["ctx"]
    assert "foo=bar" in extra["ctx"]


def test_level_filtering_drops_below_min(capsys):
    configure_logging(Settings(_env_file=None, environment="production", log_level="WARNING"))
    log = structlog.get_logger("svc")
    log.info("should_be_dropped")
    log.warning("should_appear")

    out = capsys.readouterr().out
    assert "should_be_dropped" not in out
    assert "should_appear" in out


def test_stdlib_logging_is_intercepted_into_pipeline(capsys):
    configure_logging(Settings(_env_file=None, environment="production", log_level="DEBUG"))
    logging.getLogger("some.third.party").warning("from stdlib")

    out = capsys.readouterr().out
    assert "from stdlib" in out
    # It went through the JSON renderer, so the line parses as JSON.
    line = [l for l in out.splitlines() if "from stdlib" in l][-1]
    assert json.loads(line)["event"] == "from stdlib"
