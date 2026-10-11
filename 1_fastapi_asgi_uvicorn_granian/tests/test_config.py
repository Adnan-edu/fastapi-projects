from app.core.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.app_name == "fastapi-asgi-demo"
    assert s.app_host == "0.0.0.0"
    assert s.app_port == 8000
    assert s.workers == 1


def test_settings_override_from_env(monkeypatch):
    monkeypatch.setenv("APP_NAME", "custom-app")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("WORKERS", "4")
    s = Settings()
    assert s.app_name == "custom-app"
    assert s.app_port == 9000
    assert s.workers == 4


def test_settings_invalid_port(monkeypatch):
    monkeypatch.setenv("APP_PORT", "not-a-number")
    try:
        Settings()
        assert False, "Should have raised validation error"
    except Exception:
        pass