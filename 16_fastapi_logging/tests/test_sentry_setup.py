"""Tests for app.sentry_setup.init_sentry (graceful no-op without DSN)."""
import app.sentry_setup as sentry_setup
from app.config import Settings


def test_no_dsn_skips_init(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_setup.sentry_sdk, "init", lambda **kw: calls.append(kw))

    enabled = sentry_setup.init_sentry(Settings(_env_file=None, sentry_dsn=None))

    assert enabled is False
    assert calls == []


def test_empty_dsn_skips_init(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_setup.sentry_sdk, "init", lambda **kw: calls.append(kw))

    enabled = sentry_setup.init_sentry(Settings(_env_file=None, sentry_dsn=""))

    assert enabled is False
    assert calls == []


def test_with_dsn_initializes(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_setup.sentry_sdk, "init", lambda **kw: calls.append(kw))

    enabled = sentry_setup.init_sentry(
        Settings(
            _env_file=None,
            sentry_dsn="https://k@o123.ingest.sentry.io/1",
            environment="production",
            app_version="9.9.9",
        )
    )

    assert enabled is True
    assert len(calls) == 1
    kw = calls[0]
    assert kw["dsn"] == "https://k@o123.ingest.sentry.io/1"
    assert kw["environment"] == "production"
    assert kw["release"] == "9.9.9"
    assert kw["integrations"]  # FastApiIntegration attached
