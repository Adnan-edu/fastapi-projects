"""End-to-end integration tests for the FastAPI application routers and middleware."""
import json  # Import json module for parsing JSON strings
import pytest  # Import pytest framework for assertion and test fixtures
from fastapi.testclient import TestClient  # Import FastAPI TestClient to query endpoints
import structlog  # Import structlog for logging configurations reset

from app.config import Settings  # Import Settings config mapping class
from app.main import create_app  # Import main app creator factory function
from app.services.payment import PaymentGatewayError  # Import custom payment gateway exception class


@pytest.fixture(autouse=True)  # Register autouse fixture running on every test case
def clean_logging():  # Reset global logging configurations to keep tests isolated
    """Auto-use fixture to reset structlog defaults after each test case."""
    yield  # Suspend execution until the test completes
    structlog.reset_defaults()  # Reset default logging handlers after the test finishes


def test_health_endpoint(client: TestClient):  # Test function mapping GET /health
    """Test GET /health healthcheck endpoint."""
    response = client.get("/health")  # Trigger request to /health route
    assert response.status_code == 200  # Assert returned status code is 200
    assert response.json() == {"status": "ok"}  # Assert JSON response matches status ok dict


def test_get_user_success(client: TestClient):  # Test user query path success case
    """Test GET /users/{user_id} when user exists."""
    response = client.get("/users/1")  # Trigger request to users/1
    assert response.status_code == 200  # Assert returned status code is 200
    assert response.json() == {"user_id": 1, "username": "ada"}  # Assert name mapping is correct


def test_get_user_not_found(client: TestClient):  # Test user query 404 path
    """Test GET /users/{user_id} when user does not exist."""
    response = client.get("/users/999")  # Request non-existent user ID 999
    assert response.status_code == 404  # Assert status code is 404 Not Found
    assert response.json() == {"detail": "user not found"}  # Assert error payload contains user not found detail


def test_login_success(client: TestClient):  # Test successful login query logic
    """Test POST /users/login with correct credentials."""
    response = client.post("/users/login", json={"user_id": 1, "password": "pwd"})  # Submit login POST payload
    assert response.status_code == 200  # Assert code is 200 OK
    assert response.json() == {"user_id": 1, "status": "ok"}  # Assert outcome details mapping


def test_login_failure(client: TestClient):  # Test login authentication validation failure case
    """Test POST /users/login with incorrect credentials."""
    response = client.post("/users/login", json={"user_id": 999, "password": "pwd"})  # Submit incorrect credentials
    assert response.status_code == 401  # Assert status code is 401 Unauthorized
    assert response.json() == {"detail": "invalid credentials"}  # Assert error details mapping


def test_payments_success(client: TestClient):  # Test successful gateway charge route
    """Test POST /payments with valid amount."""
    response = client.post("/payments", json={"user_id": 123, "amount": 100.50})  # Request positive amount transaction
    assert response.status_code == 200  # Assert status is 200 OK
    payload = response.json()  # Parse response body dictionary
    assert payload["user_id"] == 123  # Verify receipt matches user ID parameter
    assert payload["amount"] == 100.50  # Verify receipt matches amount parameter
    assert payload["status"] == "succeeded"  # Verify status label is succeeded
    assert "transaction_id" in payload  # Assert presence of transaction ID string token


def test_payments_failure(client: TestClient, sentry_spy):  # Test payment failure path
    """Test POST /payments with amount over limit, triggering handled exception."""
    response = client.post("/payments", json={"user_id": 123, "amount": 500_000.00})  # Request over limit amount
    assert response.status_code == 402  # Assert status is 402 Payment Required
    assert "exceeds limit" in response.json()["detail"]  # Assert error details mention limit exceeded

    # Verify handled exception was captured in Sentry
    assert len(sentry_spy) == 1  # Assert that Sentry captured exactly one exception object
    assert isinstance(sentry_spy[0], PaymentGatewayError)  # Assert exception captured matches PaymentGatewayError class


def test_boom_endpoint(client: TestClient, sentry_spy):  # Test simulated crash routing logic
    """Test GET /boom endpoint triggers unhandled ValueError and 500 status."""
    response = client.get("/boom")  # Trigger simulated unhandled crash request
    assert response.status_code == 500  # Assert client receives status 500 Internal Server Error
    assert response.json() == {"detail": "Internal Server Error"}  # Assert returned payload matches error detail format

    # Verify unhandled exception was captured in Sentry
    assert len(sentry_spy) == 1  # Assert Sentry captured exactly one exception object
    assert isinstance(sentry_spy[0], ValueError)  # Assert exception object matches ValueError class type
    assert str(sentry_spy[0]) == "intentional unhandled error for Sentry/observability demo"  # Verify exact crash message trace


def test_request_id_propagation(client: TestClient):  # Verify ID header mapping and auto generation
    """Verify X-Request-ID header propagation and generation."""
    # 1. Propagation of incoming request ID
    response = client.get("/health", headers={"X-Request-ID": "custom-uuid-123"})  # Pass custom tracing ID in headers
    assert response.status_code == 200  # Verify 200 OK health status
    assert response.headers.get("X-Request-ID") == "custom-uuid-123"  # Verify custom ID was returned in response headers

    # 2. Generation of request ID when missing
    response_gen = client.get("/health")  # Trigger query request omitting header ID
    assert response_gen.status_code == 200  # Verify status OK
    generated_id = response_gen.headers.get("X-Request-ID")  # Extract response header ID string
    assert generated_id is not None  # Assert presence of header string
    assert len(generated_id) > 0  # Assert string is not empty


def test_production_json_logging(capsys):  # Verify production logging outputs JSON
    """E2E test to verify production environment writes parseable JSON lines to stdout."""
    prod_settings = Settings(  # Construct production config payload
        _env_file=None,  # Skip reading local env variables
        environment="production",  # Enable production mode to trigger JSONRenderer logging output
        log_level="INFO",  # Set log level to INFO
        sentry_dsn="",  # Set blank Sentry DSN target to skip initialization
    )
    prod_app = create_app(prod_settings)  # Instantiate production application
    prod_client = TestClient(prod_app, raise_server_exceptions=False)  # Instantiate client with propagation disabled

    # Invoke GET /health which produces logs in the request middleware
    response = prod_client.get("/health")  # Query healthcheck route
    assert response.status_code == 200  # Verify OK status

    # Capture standard output
    captured = capsys.readouterr().out.strip()  # Capture standard output text stream
    assert captured, "Expected production logs printed to stdout"  # Assert log line was captured in stdout

    lines = captured.splitlines()  # Split stdout block into distinct lines
    events = []  # Instantiate local array list to map parsed logs
    for line in lines:  # Loop over captured log output lines
        try:  # Attempt JSON mapping parsing block
            data = json.loads(line)  # Parse string log entry into JSON dictionary representation
            events.append(data)  # Append data dictionary to events list
        except json.JSONDecodeError:  # Intercept non-JSON log structures
            # Skip any logs or prints that are not JSON formatted
            continue  # Continue loop iteration

    # Ensure middleware logs request_started and request_completed
    assert len(events) >= 2  # Verify we captured at least two distinct events
    started = [e for e in events if e.get("event") == "request_started"]  # Filter event dict matching started tag
    completed = [e for e in events if e.get("event") == "request_completed"]  # Filter event dict matching completed tag

    assert started, "Expected request_started event in production JSON log output"  # Assert request_started exists
    assert completed, "Expected request_completed event in production JSON log output"  # Assert request_completed exists

    # Verify context propagation of the generated request_id
    req_id_started = started[0].get("request_id")  # Extract request ID from start log
    req_id_completed = completed[0].get("request_id")  # Extract request ID from end log

    assert req_id_started is not None  # Assert request ID exists
    assert req_id_started == req_id_completed  # Verify start and end logs share matching request trace IDs

