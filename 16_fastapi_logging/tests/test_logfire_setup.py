"""Tests for app.logfire_setup.init_logfire (graceful no-op without token)."""
import app.logfire_setup as logfire_setup
from app.config import Settings


def test_no_token_skips_init(monkeypatch):
    calls = []
    monkeypatch.setattr(logfire_setup.logfire, "configure", lambda **kw: calls.append(kw))

    enabled = logfire_setup.init_logfire(Settings(_env_file=None, logfire_token=None))

    assert enabled is False
    assert calls == []


def test_empty_token_skips_init(monkeypatch):
    calls = []
    monkeypatch.setattr(logfire_setup.logfire, "configure", lambda **kw: calls.append(kw))

    enabled = logfire_setup.init_logfire(Settings(_env_file=None, logfire_token=""))

    assert enabled is False
    assert calls == []


def test_with_token_initializes_and_instruments_app(monkeypatch):
    config_calls = []
    monkeypatch.setattr(logfire_setup.logfire, "configure", lambda **kw: config_calls.append(kw))

    instrument_calls = []
    monkeypatch.setattr(logfire_setup.logfire, "instrument_fastapi", lambda app: instrument_calls.append(app))

    settings = Settings(
        _env_file=None,
        logfire_token="lf-test-token",
        environment="production",
        app_version="9.9.9",
    )
    from fastapi import FastAPI

    app = FastAPI()
    enabled = logfire_setup.init_logfire(settings, app)

    assert enabled is True
    assert len(config_calls) == 1
    kw = config_calls[0]
    assert kw["token"] == "lf-test-token"
    assert kw["service_name"] == "fastapi-logging-demo"
    assert kw["environment"] == "production"
    assert kw["service_version"] == "9.9.9"
    assert len(instrument_calls) == 1
    assert instrument_calls[0] is app


def test_init_without_app_skips_instrumentation(monkeypatch):
    config_calls = []
    monkeypatch.setattr(logfire_setup.logfire, "configure", lambda **kw: config_calls.append(kw))

    instrument_calls = []
    monkeypatch.setattr(logfire_setup.logfire, "instrument_fastapi", lambda app: instrument_calls.append(app))

    settings = Settings(
        _env_file=None,
        logfire_token="lf-test-token",
    )
    enabled = logfire_setup.init_logfire(settings, app=None)

    assert enabled is True
    assert len(config_calls) == 1
    assert len(instrument_calls) == 0