# FastAPI Observability Stack — Loguru + Structlog + Sentry

**Date:** 2026-06-13
**Status:** Approved

## Goal

Build an end-to-end FastAPI project that demonstrates the three logging/observability
tools from `python_logging_3tools.md`:

- **Loguru** — developer-friendly colored console + rotating/retained/compressed log files.
- **Structlog** — structured, queryable JSON logs for production, with per-request context binding.
- **Sentry** — error monitoring/alerting for handled and unhandled exceptions.

The deliverables are: a working app, an end-to-end test suite, and a README with box diagrams.

## Architecture — one unified, env-switched log pipeline

`structlog.get_logger()` is the single logging API used everywhere. The **final renderer**
is chosen by the `ENVIRONMENT` setting:

- `development` → the event is handed to a **Loguru** sink that owns the colored console and
  the rotating log files (`logs/app.log`, `logs/errors.log`).
- `production` → structlog's `JSONRenderer` writes one JSON line per event to stdout
  (ready for Datadog / Grafana Loki / CloudWatch).

An `InterceptHandler` redirects stdlib `logging` and uvicorn loggers into the same pipeline,
producing a single coherent log stream. Sentry initializes in any environment when a DSN
is present, and cleanly no-ops when it is absent.

```
incoming request -> RequestContextMiddleware (mint request_id, bind contextvars, time + log)
                 -> structlog.get_logger()  (the ONE logging API)
                 -> structlog processor chain (merge contextvars, level, name, ts, exc_info)
   dev  -> Loguru sink: colored console + logs/app.log (INFO) + logs/errors.log (ERROR, backtrace+diagnose)
   prod -> structlog JSONRenderer -> stdout
stdlib + uvicorn logs -> InterceptHandler -> same pipeline
unhandled exception   -> Sentry (if DSN) + error log
```

## Components / file layout

```
app/
  __init__.py
  main.py            # create_app(): wires config, logging, sentry, middleware, routers, exc handler
  config.py          # pydantic-settings: ENVIRONMENT, LOG_LEVEL, SENTRY_DSN, APP_VERSION, log dirs
  logging_config.py  # configure_logging(): structlog chain + Loguru sinks + InterceptHandler
  context.py         # contextvar helpers: bind_request_context / clear / get_request_id
  sentry_setup.py    # init_sentry(): graceful no-op when DSN absent
  middleware.py      # RequestContextMiddleware
  routers/
    users.py         # GET /users/{id}, POST /users/login
    payments.py      # POST /payments (handled PaymentGatewayError + capture_exception)
    system.py        # GET /health, GET /boom (unhandled -> Sentry)
  services/
    payment.py       # PaymentGateway + PaymentGatewayError
tests/
logs/                # gitignored, created at runtime
.env.example
README.md
```

## Behaviors

- **Context binding (Structlog):** middleware binds `request_id`, `method`, `path`; routers add
  `user_id`. Every event in that request carries the bound fields via `structlog.contextvars`.
- **Dev output (Loguru):** colored console + `logs/app.log` (INFO, rotation `100 MB`,
  retention `30 days`, zip compression) + `logs/errors.log` (ERROR, `backtrace=True`, `diagnose=True`).
- **Prod output (Structlog):** JSON lines to stdout with full bound context
  (`request_started` / `request_completed` shape).
- **Sentry:** `init_sentry()` adds `FastApiIntegration`. `/payments` uses the handled-exception
  pattern (`logger.error(...)` + `sentry_sdk.capture_exception(e)` + re-raise). `/boom` raises an
  unhandled error captured globally. No DSN → clean skip with a notice.

## Error handling

- Missing `SENTRY_DSN` → `init_sentry()` logs a notice and returns; app fully functional.
- `logs/` directory auto-created; file sinks added only when the path is writable.
- A global exception handler logs unhandled errors with full bound context before returning 500.

## Testing (pytest, TDD)

- Use `structlog.testing` capture and `capsys` to assert events and bound fields.
- Cases:
  - `request_id` is present and propagates across multiple log lines within one request.
  - `GET /health` → 200.
  - `GET /users/{id}` logs bound `user_id`.
  - `POST /payments` failure path calls `capture_exception` (Sentry mocked; never hits network).
  - `GET /boom` → 500 and capture invoked.
  - Production mode emits valid, parseable JSON per line.
  - Development mode routes through the Loguru sink.
  - `init_sentry()` no-ops without a DSN.
- Sentry is always mocked in tests — no real network calls.

## Tooling

- Package manager: **uv**. Virtualenv: `fastapi_logging/`.
- Dependencies: `fastapi`, `uvicorn[standard]`, `loguru`, `structlog`, `sentry-sdk[fastapi]`,
  `pydantic-settings`, `httpx` (test client), `pytest`, `pytest-asyncio`.
