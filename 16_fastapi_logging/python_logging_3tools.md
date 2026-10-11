# I Fixed My Python Logging With 3 Tools. Here Is How.

Default Python logging works. It just does not work well enough when something breaks at 2am in production.

---

Debugging a production issue at two in the morning is already exhausting. Doing it while scrolling through thousands of lines of messy logs and trying to reconstruct what happened makes you question every choice that led there.

That was my reality with Python's default logging. It produced output, but not useful insight. Timestamps were inconsistent, formats varied between modules, and tracing one request felt like solving a mystery.

I was spending four to six hours each week chasing issues that clear, structured logs could have revealed in minutes.

I replaced the entire setup with three tools. Here is what I chose, how I set each one up, and what the actual difference looked like.

---

## Why Default Python Logging Was Not Enough

Before getting into the tools, it is worth being specific about what default logging fails at because the problems are not always obvious until you are already in trouble.

The default logging module produces output like this:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("User login attempt")
logger.error("Database connection failed")
```

Output:

```
INFO:__main__:User login attempt
ERROR:__main__:Database connection failed
```

This is readable in a terminal during development. In production, where you have multiple services, multiple workers, and thousands of events per minute, it becomes noise. There is no request context, no structured data you can query, no color differentiation between severity levels in development, and no easy way to send logs to external monitoring systems without significant additional configuration.

The three tools below each solve a different layer of this problem.

---

## Tool 1: Loguru

Loguru is the tool that should have been Python's default logging library. It replaces the entire default logging setup with a single import, requires zero configuration to produce useful output immediately, and handles the things that require significant boilerplate in the standard library automatically.

```python
from loguru import logger
logger.info("User login attempt")
logger.warning("Rate limit approaching for user {user_id}", user_id=123)
logger.error("Database connection failed")
logger.debug("Query executed in {time}ms", time=45)
```

Output in development:

```
2026-02-26 14:23:01.432 | INFO     | main:login:42 - User login attempt
2026-02-26 14:23:01.433 | WARNING  | main:login:43 - Rate limit approaching for user 123
2026-02-26 14:23:01.434 | ERROR    | main:login:44 - Database connection failed
2026-02-26 14:23:01.435 | DEBUG    | main:login:45 - Query executed in 45ms
```

Color-coded by severity in the terminal. Includes the exact file, function, and line number automatically. Structured variable interpolation built in. No additional configuration required to get this output.

Where Loguru becomes genuinely powerful is in its file rotation and retention configuration:

```python
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    colorize=True
)
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    rotation="100 MB",
    retention="30 days",
    compression="zip",
    level="INFO",
    format="{time} | {level} | {name}:{function}:{line} | {message}"
)
logger.add(
    "logs/errors_{time:YYYY-MM-DD}.log",
    rotation="50 MB",
    retention="60 days",
    level="ERROR",
    backtrace=True,
    diagnose=True
)
```

The backtrace and diagnose options on the error logger are worth highlighting specifically. When an exception occurs, Loguru captures the full stack trace including the values of local variables at each frame. That single feature eliminated a significant portion of my reproduce-to-debug cycle because I could see exactly what values caused the crash without recreating the conditions.

---

## Tool 2: Structlog

Loguru solved my development logging problem. Structlog solved my production logging problem, which is a different challenge entirely.

In production, logs need to be queryable. You need to search by user ID, by request ID, by endpoint, by error type, without reading through raw text. Structlog produces structured JSON output that log aggregation platforms like Datadog, Grafana Loki, and AWS CloudWatch can index and query natively.

```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
```

What makes Structlog different is context binding. You bind contextual data to the logger at the start of a request and every subsequent log event in that request automatically includes that context:

```python
import structlog
import uuid

logger = structlog.get_logger()

def handle_request(user_id: int, endpoint: str):
    request_id = str(uuid.uuid4())
    log = logger.bind(
        request_id=request_id,
        user_id=user_id,
        endpoint=endpoint
    )
    log.info("request_started")
    try:
        result = process_request(user_id)
        log.info("request_completed", status="success", result_count=len(result))
        return result
    except Exception as e:
        log.error("request_failed", error=str(e), error_type=type(e).__name__)
        raise
```

JSON output:

```json
{"event": "request_started", "request_id": "a3f2...", "user_id": 123, "endpoint": "/api/users", "timestamp": "2026-02-26T14:23:01Z", "level": "info"}
{"event": "request_completed", "request_id": "a3f2...", "user_id": 123, "endpoint": "/api/users", "status": "success", "result_count": 47, "level": "info"}
```

Every log line carries full context. Searching for all events related to a specific request ID becomes a single query in any log platform instead of a manual grep through text files.

---

## Tool 3: Sentry

Loguru handles development visibility. Structlog handles production queryability. Sentry handles the thing neither of them covers: alerting you when something goes wrong before a user reports it.

Sentry is an error monitoring platform that captures exceptions, groups them by type and stack trace, tracks their frequency, and sends alerts when new error types appear or when error rates spike. The Python SDK integrates in about five minutes:

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import os

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[
        FastApiIntegration(transaction_style="endpoint"),
        SqlalchemyIntegration(),
    ],
    traces_sample_rate=0.2,
    profiles_sample_rate=0.1,
    environment=os.environ.get("ENVIRONMENT", "production"),
    release=os.environ.get("APP_VERSION", "unknown"),
)
```

After this, every unhandled exception in your application is automatically captured and sent to Sentry with the full stack trace, request context, user information, and breadcrumbs showing what happened before the error occurred.

For handled exceptions you want to track explicitly:

```python
import sentry_sdk
from loguru import logger

def process_payment(user_id: int, amount: float):
    try:
        result = payment_gateway.charge(user_id, amount)
        return result
    except PaymentGatewayError as e:
        logger.error(f"Payment failed for user {user_id}: {str(e)}")
        sentry_sdk.capture_exception(e)
        raise
```

The combination of local logging with Loguru and error monitoring with Sentry means you have two independent records of every failure. The local log is for immediate debugging. The Sentry event is for pattern detection, frequency tracking, and alerting.

---

## How the Three Tools Work Together

The stack covers three completely separate concerns with no meaningful overlap:

- **Loguru** improves local development with clear, color-coded, context-rich logs that make debugging quick and simple.
- **Structlog** manages production logging using structured JSON, making logs easy to search and integrate with monitoring tools.
- **Sentry** provides error tracking and alerts so you learn about issues before users do.

Setting up all three takes less than an hour and adds no noticeable overhead. Together, they replaced a logging setup that cost me four to six hours of debugging each week with one that reveals most problems in under ten minutes.

---

## What Actually Changed

Loguru makes local development easier with clear, color-coded logs that speed up debugging. Structlog organizes production logs into structured JSON, making them easy to search and connect with monitoring tools. Sentry tracks errors and sends alerts so you know about issues before users do.

Setup takes under an hour with no real performance cost. It cut my weekly debugging time from several hours to about ten minutes.
