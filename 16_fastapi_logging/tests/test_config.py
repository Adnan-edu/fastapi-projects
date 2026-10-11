"""Tests for app.config.Settings / get_settings."""
from app.config import Settings, get_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.environment == "development"
    assert s.log_level == "DEBUG"
    assert s.sentry_dsn is None
    assert s.app_version == "0.1.0"
    assert s.log_dir == "logs"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("SENTRY_DSN", "https://abc@example.com/1")
    s = Settings(_env_file=None)
    assert s.environment == "production"
    assert s.log_level == "WARNING"
    assert s.sentry_dsn == "https://abc@example.com/1"


def test_is_production_helper():
    assert Settings(_env_file=None, environment="production").is_production is True
    assert Settings(_env_file=None, environment="development").is_production is False


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
