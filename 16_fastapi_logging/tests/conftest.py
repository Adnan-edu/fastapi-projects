"""Pytest configuration and global fixtures."""
import pytest  # Import pytest framework for testing configurations and fixtures
from fastapi.testclient import TestClient  # Import FastAPI test client helper class
import sentry_sdk  # Import Sentry SDK module to mock integrations

from app.config import Settings  # Import settings schema configurations
from app.main import create_app  # Import main app creator factory function


@pytest.fixture  # Register pytest settings fixture
def test_settings() -> Settings:  # Return settings structure for test environment
    """Provide a Settings instance configured for testing."""
    return Settings(  # Construct Settings object for unit tests
        _env_file=None,  # Do not read from root .env file to prevent local setting leaks
        environment="development",  # Set target environment to development
        log_level="DEBUG",  # Capture granular logs down to DEBUG severity
        sentry_dsn="",  # Set blank Sentry DSN target to skip initialization
        logfire_token="",  # Set blank Logfire token to skip initialization
        log_dir="test_logs",  # Redirect file logs target to test_logs folder
    )


@pytest.fixture  # Register pytest app fixture
def app(test_settings: Settings):  # Accept configured test_settings fixture as input parameter
    """Provide a test application instance."""
    return create_app(test_settings)  # Call factory to build a configured app instance


@pytest.fixture  # Register pytest client fixture
def client(app) -> TestClient:  # Accept app instance fixture as input parameter
    """Provide a TestClient for making requests to the app."""
    return TestClient(app, raise_server_exceptions=False)  # Instantiate test client with exception propagation disabled


@pytest.fixture  # Register pytest sentry spy fixture
def sentry_spy(monkeypatch):  # Accept monkeypatch context manager fixture
    """Spy on Sentry's capture_exception to assert it was called correctly."""
    captured_exceptions = []  # Instantiate local array list to record exceptions

    def mock_capture(exc, *args, **kwargs):  # Define mock replacement capture function
        captured_exceptions.append(exc)  # Push captured exception to recording list
        return "mocked-event-id"  # Return mock success event token ID string

    monkeypatch.setattr(sentry_sdk, "capture_exception", mock_capture)  # Override sentry_sdk.capture_exception with mock function
    return captured_exceptions  # Return the list recording captured exception pointers

