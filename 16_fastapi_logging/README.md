# FastAPI Unified Logging & Observability Stack

An end-to-end FastAPI project demonstrating a production-grade observability pipeline integrating **Loguru**, **Structlog**, **Sentry**, and **Pydantic Logfire**.

This setup addresses the limits of default Python logging by providing a single, unified logging stream with automatic request-context propagation, environment-specific rendering, reliable error tracking, and SQL-queryable distributed tracing.

---

## High-Level Overview

This project implements four essential observability concerns with zero overlap:

1. **Loguru (Development Visibility)**: Provides color-coded, developer-friendly terminal output and maintains rotating, compressed file logs (`logs/app.log` and `logs/errors.log`). Captures full traceback local variables for zero-friction debugging.
2. **Structlog (Production Queryability)**: Structured logging with context-binding. Collects request state (endpoints, user IDs, request durations, and request IDs) and renders it as single-line JSON strings to `stdout` for ingestion by platforms like Datadog, Grafana Loki, or AWS CloudWatch.
3. **Sentry (Error Monitoring & Alerting)**: Automatic capturing of unhandled crashes and selective capturing of handled exceptions (e.g. payment gateway failures) alongside bound context breadcrumbs.
4. **Pydantic Logfire (Distributed Tracing & Observability)**: Automatic FastAPI request/response tracing, span-based instrumentation, and real-time log forwarding to the Logfire web console. All structlog events flow to Logfire via `StructlogProcessor`, and handled exceptions are recorded in spans via `record_exception`. Gracefully disabled when `LOGFIRE_TOKEN` is absent.

---

## Architectural & Flow Diagrams

### 1. Unified Logging Pipeline Architecture

All application events, standard library logs, and Uvicorn server logs flow into a single pipeline managed by `structlog`. The pipeline formats the message and merges request-scoped context variables, then renders the output according to the environment.

```
+-------------------------------------------------------------------------------+
|                             LOG INGESTION LAYER                               |
+-------------+---------------------------+-----------------------+-------------+
| FastAPI App | Custom Middleware/Service | Stdlib logging module | Uvicorn log |
+------+------+-------------+-------------+-----------+-----------+------+------+
       |                    |                         |                  |
       v                    v                         v                  v
+-------------------------------------------------------------------------------+
|                      InterceptHandler / structlog.get_logger()                |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                           SHARED PROCESSOR PIPELINE                           |
|  1. Merge Contextvars (request_id, user_id, method, path...)                  |
|  2. Add Log Level                                                             |
|  3. Add Logger Name                                                           |
|  4. Format ISO Timestamp                                                      |
|  5. Format Exceptions / Stacktrace info                                       |
|  6. Logfire StructlogProcessor  <--- NEW: forwards events to Logfire          |
+---------------------------------------+---------------------------------------+
                                        |
                      Is ENVIRONMENT == "production"?
                               /        \
                             Yes         No
                             /             \
                            v               v
            +----------------------+  +------------------------------------+
            |  structlog Renderer  |  |         Loguru Sinks               |
            |   (JSONRenderer)    |  | - Console FMT (Colorized)          |
            +----------+-----------+  | - app.log (INFO, 100MB rotation)   |
                       |              | - errors.log (ERROR, backtrace/    |
                       v              |               diagnose, 50MB rot)  |
                     stdout           +-----------------+------------------+
             (Datadog/Loki/etc.)                        |
                                                        v
                                                   Log Files
```

### 2. End-to-End Request Context Flow

Every request receives a unique `request_id` (propagated from upstream headers or generated automatically). This context variables state is shared thread-safely across asynchronous bounds via Python's `contextvars`.

```
[ Client ]                 [ Middleware ]               [ Router/Service ]         [ Pipeline ]
    |                            |                              |                       |
    |----( HTTP Request )------->|                              |                       |
    |                            |-- ( Mint request_id )        |                       |
    |                            |-- ( Bind contextvars ) ------>[ Context Store ]       |
    |                            |                              |       |               |
    |                            |-- ( Log request_started ) ----------->|               |
    |                            |                              |       |-- ( Merges )->| (Logs JSON/Console)
    |                            |----( Forward Request )------>|       |               |
    |                            |                              |-- (Bind user_id)      |
    |                            |                              |-- (Log endpoint)----->| (Logs with req_id
    |                            |                              |       |-- ( Merges )->|  and user_id)
    |                            |                              |<-- (Return response)  |
    |                            |<---( Return Response )-------|       |               |
    |                            |-- ( Log request_completed ) ------------------------>| (Logs with timing)
    |                            |-- ( Attach X-Request-ID )    |       |               |
    |                            |-- ( Clear Contextvars ) ---->[ Context Store ]       |
    |<---( HTTP Response )-------|                                      |               |
         (X-Request-ID: abc)                                         (Cleared)
```

---

## Directory Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py           # Pydantic-settings config schema & loader
│   ├── context.py          # Request-scoped contextvar binding helpers
│   ├── logfire_setup.py    # Pydantic Logfire initialization & FastAPI instrumentation
│   ├── logging_config.py   # Unified pipeline setup & env-specific sinks
│   ├── main.py             # FastAPI app builder & wiring
│   ├── middleware.py       # RequestContextMiddleware for timing & request-ids
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── payments.py     # Handles endpoint (handled errors to Sentry & Logfire)
│   │   ├── system.py       # Health checks and deliberate crash endpoints
│   │   └── users.py        # User verification & login endpoints
│   └── services/
│       ├── __init__.py
│       └── payment.py      # Mocked payment gateway service logic
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # Pytest fixtures and Sentry mock configurations
│   ├── test_app.py         # Comprehensive E2E tests for API & logging
│   ├── test_config.py      # Unit tests for settings
│   ├── test_context.py     # Unit tests for contextvar wrappers
│   ├── test_logfire_setup.py # Unit tests for Logfire configuration behavior
│   ├── test_logging_config.py # Unit tests for log pipeline & stdout rendering
│   ├── test_payment.py     # Unit tests for payment service
│   └── test_sentry_setup.py # Unit tests for Sentry configuration behavior
├── .env.example            # Environment variables configuration guide
├── pyproject.toml          # uv configuration and dependencies
├── python_logging_3tools.md # Original design reference document
└── README.md               # Project documentation
```

---

## Setup & Running Guide

### Prerequisites
- Python >= 3.12
- [uv](https://github.com/astral-sh/uv) (Extremely fast Python package manager)

### 1. Install Dependencies

Install project dependencies and build the virtual environment using `uv`:

```bash
uv sync
```

### 2. Configure Environment Variables

Copy the `.env.example` file to `.env` and adjust settings as desired:

```bash
cp .env.example .env
```

Default variables configured in `.env.example`:
- `ENVIRONMENT=development` (Switch to `production` to toggle JSON format)
- `LOG_LEVEL=DEBUG`
- `SENTRY_DSN=` (Leave blank to disable Sentry cleanly)
- `APP_VERSION=0.1.0`
- `LOG_DIR=logs`
- `LOGFIRE_TOKEN=` (Leave blank to disable Logfire cleanly)

### 3. Run the Application

Start the FastAPI application via `main.py` using `uv`:

```bash
uv run python main.py
```

The server will start at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## Interactive Endpoint Guide

| Method | Endpoint | Description | Observability Details |
| :--- | :--- | :--- | :--- |
| **GET** | `/health` | Server status check | Emits `health_check` event at `DEBUG` level. |
| **GET** | `/users/{user_id}` | Retrieve mock user profile | Binds `user_id` context variable. Logs `fetch_user` and `user_fetched` / `user_not_found` (404 warning). |
| **POST** | `/users/login` | Simulate user authentication | Binds `user_id`. Logs `login_attempt` and status outcome (200 success / 401 warning). |
| **POST** | `/payments` | Create payment charge | Binds `user_id` and `amount`. Demonstrates **handled exception pattern** (errors log at `ERROR` level, report to Sentry via `capture_exception`, record in Logfire span via `record_exception`, returning clean HTTP 402). |
| **GET** | `/boom` | Simulate an unhandled exception | Raises `ValueError`. Middleware catches the error, logs the full stacktrace at `ERROR` level, forwards the exception to Sentry, and returns clean HTTP 500. |

---

## Verification & Testing

The project has a comprehensive test suite covering standard configuration parsing, contextvar isolation, pipeline redirection, payment gateway boundaries, and full API integrations.

### Running Tests

Execute the full suite of unit and E2E tests using `uv`:

```bash
uv run pytest
```

Example test output:

```
============================== 30 passed in 0.26s ==============================
```

### End-to-End Tracing Tests

Key test scenarios implemented in [tests/test_app.py](file:///Users/mdashikadnan/Documents/adnanedu/python/medium/fastapi_projects/16_fastapi_logging/tests/test_app.py) verify that:
1. **X-Request-ID Header Propagation**: If an `X-Request-ID` is passed by a client (e.g. from an API gateway), it is preserved and returned. Otherwise, a UUID request ID is generated.
2. **Context Persistence**: The same request ID persists across every single log entry triggered during that request.
3. **JSON Output Compliance**: In `production` mode, logs output valid single-line JSON structure containing standard context variables.
4. **Sentry Monitoring**: Handler captures exception details for `/payments` failures (HTTP 402) and `/boom` exceptions (HTTP 500) without leaking credentials or performing actual network requests.

---

## Pydantic Logfire Integration (Step-by-Step)

Pydantic Logfire adds distributed tracing, SQL-queryable log analytics, and real-time observability to this project. It integrates alongside the existing Loguru + Structlog + Sentry stack without replacing any component.

### What Logfire Provides

- **Automatic FastAPI Request Tracing**: `logfire.instrument_fastapi(app)` creates a trace span for every incoming HTTP request, recording method, path, status code, and duration -- no manual instrumentation needed.
- **Pydantic Validation Visibility**: Automatically captures request-body validation errors with the exact fields that failed and why, so you can see malformed payloads in the Logfire dashboard.
- **SQL-Queryable Logs**: All structlog events (including `request_id`, `user_id`, `amount`) flow to Logfire via `StructlogProcessor`. You can query them with SQL in the Logfire web console (e.g. `SELECT * FROM records WHERE level = 'error'`).
- **Handled Exception Recording**: `span.record_exception(exc)` inside a `logfire.span` context attaches the exception and its stack trace to the span, making handled failures (like payment gateway rejections) visible in traces alongside unhandled crashes.
- **Graceful No-Op Fallback**: When `LOGFIRE_TOKEN` is empty or absent, `init_logfire()` returns `False` and the application runs normally with Loguru + Structlog + Sentry only.

### Step-by-Step Setup

#### Step 1: Create a Logfire Account and Project

1. Go to [https://logfire.pydantic.dev](https://logfire.pydantic.dev) and sign up (free tier available).
2. Create a new project in the Logfire dashboard.
3. Copy the **write token** for your project.

#### Step 2: Add the Token to Your Environment

Edit your `.env` file and set `LOGFIRE_TOKEN`:

```bash
LOGFIRE_TOKEN=your-logfire-write-token-here
```

If `LOGFIRE_TOKEN` is empty or absent, Logfire is completely disabled and the app runs normally.

#### Step 3: Logfire is Already Wired In

The code changes are already in place:

| File | What It Does |
|------|-------------|
| `app/logfire_setup.py` | Calls `logfire.configure(token=...)` and `logfire.instrument_fastapi(app)` when a token is present. Returns `False` gracefully when absent. |
| `app/main.py` | Calls `init_logfire(settings, app)` after app creation and router registration. |
| `app/routers/payments.py` | Wraps payment creation in `logfire.span("create_payment", ...)` and records handled exceptions with `span.record_exception(exc)`. |
| `app/logging_config.py` | Adds `logfire.StructlogProcessor()` to the shared structlog processor pipeline so all log events flow to Logfire. |
| `app/config.py` | Reads `LOGFIRE_TOKEN` from environment / `.env`. |
| `.env.example` | Documents the `LOGFIRE_TOKEN` variable. |

#### Step 4: Run the Application

```bash
uv run python main.py
```

If `LOGFIRE_TOKEN` is set, you will see a log line like:

```
logfire_enabled  environment=development  version=0.1.0
```

If the token is absent, you will see:

```
logfire_disabled  reason=no LOGFIRE_TOKEN configured
```

#### Step 5: Explore the Logfire Dashboard

1. Open [https://logfire.pydantic.dev](https://logfire.pydantic.dev) and navigate to your project.
2. Send a payment request to trigger a span:

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "amount": 100.50}'
```

3. In the Logfire dashboard you will see:
   - A **`create_payment` span** with `user_id` and `amount` attributes.
   - All structlog events (`payment_started`, `payment_succeeded`) attached as log entries within that span.
   - The `request_id` and `user_id` from contextvars automatically included.

4. Trigger a handled failure:

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "amount": 500000}'
```

5. In Logfire you will see:
   - The same `create_payment` span but marked with an **exception event**.
   - `PaymentGatewayError` details recorded via `span.record_exception(exc)`.
   - The full stack trace and local variable values attached to the exception frame.

6. Trigger an unhandled crash:

```bash
curl http://127.0.0.1:8000/boom
```

7. Logfire automatically captures unhandled exceptions from the FastAPI instrumentation -- no manual code needed.

#### Step 6: Query Logs with SQL

In the Logfire dashboard, use SQL to query your logs and traces:

```sql
-- Find all payment failures
SELECT * FROM records
WHERE span_name = 'create_payment'
  AND level = 'error'

-- Find all requests for a specific user
SELECT * FROM records
WHERE user_id = '1'
ORDER BY timestamp DESC

-- Find slow requests (duration > 500ms)
SELECT * FROM records
WHERE duration_ms > 500
```

### How It Works Under the Hood

```
[ HTTP Request ]
       |
       v
[ FastAPI Middleware ] -----> logfire.instrument_fastapi auto-creates span
       |
       v
[ Router Handler ]
       |
       |-- logfire.span("create_payment", user_id=..., amount=...)
       |       |
       |       |-- log.info("payment_started")     (structlog -> Logfire via StructlogProcessor)
       |       |-- _gateway.charge()
       |       |       |-- Success -> logfire.info("payment_succeeded") + log.info(...)
       |       |       |-- PaymentGatewayError -> span.record_exception(exc)
       |       |                                       + sentry_sdk.capture_exception(exc)
       |       |                                       + log.error("payment_failed")
       |       |
       v
[ Response ] with X-Request-ID header
```

The `StructlogProcessor` in the shared pipeline means every structlog event (including those with bound contextvars like `request_id`, `user_id`, `method`, `path`) is automatically forwarded to Logfire -- no manual log calls needed beyond your existing `structlog.get_logger()` usage.


https://logfire-us.pydantic.dev/login