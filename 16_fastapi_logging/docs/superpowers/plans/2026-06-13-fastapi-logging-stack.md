# FastAPI Logging Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI app demonstrating Loguru (dev console + rotating files), Structlog (prod JSON + request-context binding), and Sentry (error monitoring), with an end-to-end test suite and a README with box diagrams.

**Architecture:** `structlog.get_logger()` is the single logging API. `ENVIRONMENT` selects the renderer: dev hands events to a Loguru sink (color console + rotating files); prod uses structlog `JSONRenderer` to stdout. An `InterceptHandler` routes stdlib/uvicorn logs into the same pipeline. Sentry initializes when `SENTRY_DSN` is set and no-ops otherwise.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, loguru, structlog, sentry-sdk[fastapi], pydantic-settings, pytest, pytest-asyncio, httpx.

---

### Task 1: Project setup & dependencies

**Files:** Modify `pyproject.toml`; create `.env.example`, `.gitignore`, `app/__init__.py`.

- [ ] Add deps via uv: `uv add fastapi "uvicorn[standard]" loguru structlog "sentry-sdk[fastapi]" pydantic-settings` and dev deps `uv add --dev pytest pytest-asyncio httpx`.
- [ ] `.gitignore`: `logs/`, `.env`, `__pycache__/`, `*.pyc`.
- [ ] `.env.example`: `ENVIRONMENT`, `LOG_LEVEL`, `SENTRY_DSN`, `APP_VERSION`.
- [ ] Commit.

### Task 2: Config (`app/config.py`)

**Files:** Create `app/config.py`, `tests/test_config.py`.

- [ ] Test: default `ENVIRONMENT=="development"`, `get_settings()` cached, reads env overrides.
- [ ] Implement `Settings(BaseSettings)` with `environment`, `log_level`, `sentry_dsn`, `app_version`, `log_dir`; `get_settings()` via `lru_cache`.
- [ ] Run tests, commit.

### Task 3: Request context (`app/context.py`)

**Files:** Create `app/context.py`, `tests/test_context.py`.

- [ ] Test: `bind_request_context` makes `get_request_id()` return the id; `clear_request_context()` resets.
- [ ] Implement using `structlog.contextvars.bind_contextvars` / `clear_contextvars` + a `request_id` contextvar.
- [ ] Run tests, commit.

### Task 4: Logging config (`app/logging_config.py`)

**Files:** Create `app/logging_config.py`, `tests/test_logging_config.py`.

- [ ] Test: in production mode a log call emits a single parseable JSON line to stdout containing bound `request_id`; in development mode the Loguru sink receives the record.
- [ ] Implement `configure_logging(settings)`: shared structlog processors (merge_contextvars, add_log_level, add_logger_name, TimeStamper iso, StackInfoRenderer, format_exc_info). Prod final processor = `JSONRenderer`; dev final processor = a Loguru-passthrough that calls `loguru.logger.log(...)`. Configure Loguru sinks (console colorized, `logs/app.log` INFO rotation 100MB retention 30d zip, `logs/errors.log` ERROR backtrace+diagnose). Install `InterceptHandler` on root + uvicorn loggers.
- [ ] Run tests, commit.

### Task 5: Sentry setup (`app/sentry_setup.py`)

**Files:** Create `app/sentry_setup.py`, `tests/test_sentry_setup.py`.

- [ ] Test: no DSN → `init_sentry()` returns False and does not call `sentry_sdk.init` (monkeypatched); with DSN → calls init with FastApiIntegration.
- [ ] Implement `init_sentry(settings)`.
- [ ] Run tests, commit.

### Task 6: Payment service (`app/services/payment.py`)

**Files:** Create `app/services/__init__.py`, `app/services/payment.py`, `tests/test_payment.py`.

- [ ] Test: `charge(user_id, amount)` returns dict on success (amount>0); raises `PaymentGatewayError` on amount<=0.
- [ ] Implement `PaymentGatewayError`, `PaymentGateway.charge`.
- [ ] Run tests, commit.

### Task 7: Middleware (`app/middleware.py`)

**Files:** Create `app/middleware.py`.

- [ ] Implement `RequestContextMiddleware`: mint `request_id` (uuid4), bind contextvars (request_id, method, path), log `request_started`, time request, log `request_completed` with status_code + duration_ms, add `X-Request-ID` header, clear contextvars in finally.

### Task 8: Routers

**Files:** Create `app/routers/__init__.py`, `users.py`, `payments.py`, `system.py`.

- [ ] `users.py`: `GET /users/{user_id}` binds user_id, logs, returns user; `POST /users/login` logs attempt.
- [ ] `payments.py`: `POST /payments` calls gateway; on `PaymentGatewayError` → `logger.error` + `sentry_sdk.capture_exception` + raise HTTP 402.
- [ ] `system.py`: `GET /health` → ok; `GET /boom` raises ValueError (unhandled).

### Task 9: App wiring (`app/main.py`)

**Files:** Create `app/main.py`; modify root `main.py` to run uvicorn.

- [ ] `create_app()`: load settings, configure_logging, init_sentry, add middleware, include routers, add global exception handler that logs + (capture handled by Sentry integration) returns 500.
- [ ] `app = create_app()`.

### Task 10: End-to-end tests (`tests/test_app.py`)

**Files:** Create `tests/conftest.py`, `tests/test_app.py`.

- [ ] conftest: `client` fixture (TestClient), structlog log-capture fixture, autouse monkeypatch of `sentry_sdk.capture_exception` to a spy.
- [ ] Tests: health 200; users logs bound user_id; request_id in X-Request-ID header and propagates across the request's log lines; payments success 200; payments failure 402 + capture_exception called; /boom 500 + capture; prod JSON mode emits valid JSON.
- [ ] Run full suite, commit.

### Task 11: README + final verification

**Files:** Create `README.md`.

- [ ] Box diagrams (architecture, request flow, env-switch), overview, setup with uv, run, endpoints table, env vars, testing.
- [ ] Run full test suite, run app smoke check, commit.
