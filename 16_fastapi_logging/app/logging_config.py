"""The single, env-switched logging pipeline.

``structlog.get_logger()`` is the one logging API used across the app. A shared
processor chain enriches every event (request context, level, logger name,
timestamp, exception info). The *final* step depends on ``ENVIRONMENT``:

* ``production``  -> ``JSONRenderer`` prints one JSON line per event to stdout,
  ready for Datadog / Grafana Loki / CloudWatch.
* ``development`` -> the event is handed to **Loguru**, which owns the colored
  console and the rotating, retained, compressed log files.

An :class:`InterceptHandler` redirects the standard library ``logging`` module
(and uvicorn's loggers) into this same pipeline so there is one coherent stream.
"""
import logging  # Import standard logging module to intercept logs
import sys  # Import sys to access standard out/err streams
from pathlib import Path  # Import Path for log directory creation and handling

import logfire  # Import Logfire for observability tracing and structlog integration
import structlog  # Import structlog for the primary unified logging pipeline
from loguru import logger as loguru_logger  # Import loguru to handle development outputs

from app.config import Settings  # Import Settings class for configuration options

# Shared chain applied in both environments, before the env-specific renderer.
_SHARED_PROCESSORS: list = [  # Define processors executed on every log event
    structlog.contextvars.merge_contextvars,  # Merge thread-local request variables (request_id, user_id, etc.)
    structlog.processors.add_log_level,  # Insert log level (info, debug, etc.) into the log dictionary
    structlog.stdlib.add_logger_name,  # Insert name of the logger triggering the event
    structlog.processors.TimeStamper(fmt="iso"),  # Add an ISO format timestamp to the log dictionary
    structlog.processors.StackInfoRenderer(),  # Format stack trace info if present in execution
    structlog.processors.format_exc_info,  # Format exception traceback details into human/machine readable structures
    logfire.StructlogProcessor(),  # Forward structlog events to Logfire for SQL-queryable observability
]


def _level_to_int(level: str) -> int:  # Convert string log levels (e.g. "DEBUG") to integer values
    return logging.getLevelNamesMapping().get(level.upper(), logging.INFO)  # Fetch mapped log integer from standard library mappings


def _render_to_loguru(_logger, _method_name: str, event_dict: dict):  # Custom structlog processor for dev mode Loguru forwarding
    """Final structlog processor for development: emit through Loguru.

    Pops the rendered message + level, folds the remaining structured fields
    into a ``ctx`` string, and forwards to Loguru (which colorizes the console
    and writes the rotating files). Returns ``None`` -- the no-op stdlib logger
    behind structlog discards it, so nothing is printed twice.
    """
    event = event_dict.pop("event", "")  # Extract the primary message string from event dict
    level = event_dict.pop("level", "info").upper()  # Extract the level string, fallback to info
    event_dict.pop("timestamp", None)  # Discard structlog timestamp since Loguru formats its own
    ctx = " ".join(f"{k}={v}" for k, v in event_dict.items())  # Format remaining variables into a single context string
    loguru_logger.bind(ctx=ctx).opt(depth=1).log(level, event)  # Forward formatted message and context variables to Loguru
    return event  # Return event string to satisfy interface contract


class _NamedPrintLogger(structlog.PrintLogger):  # PrintLogger extension carrying a name attribute
    """``PrintLogger`` that carries a ``name`` so ``add_logger_name`` works."""

    def __init__(self, name: str | None = None, file=None):  # Constructor accepting logger name and output target file
        super().__init__(file=file)  # Execute parent PrintLogger constructor
        self.name = name or "app"  # Store logger name, fallback to "app"


class _PrintLoggerFactory:  # Factory class to instantiate NamedPrintLogger objects
    def __init__(self, file):  # Constructor mapping target file stream
        self._file = file  # Store the target print file stream (e.g. sys.stdout)

    def __call__(self, *args):  # Callable entry point for structlog logging factory setup
        return _NamedPrintLogger(name=args[0] if args else None, file=self._file)  # Instantiates and returns NamedPrintLogger


class _NoopLogger:  # Dummy no-op logger class for dev mode to let Loguru handle printing
    """Sink for structlog in dev mode; output already went to Loguru."""

    def __init__(self, name: str | None = None):  # Constructor accepting optional name
        self.name = name or "app"  # Store logger name, fallback to "app"

    def __getattr__(self, _name):  # Catch-all attribute accessor returning callable no-op lambda
        return lambda *a, **k: None  # Return dummy function doing nothing when log operations are invoked


class _NoopLoggerFactory:  # Factory class to instantiate NoopLogger instances
    def __call__(self, *args, **kwargs):  # Callable instantiator for structlog factory binding
        return _NoopLogger(args[0] if args else None)  # Instantiates and returns a NoopLogger


class InterceptHandler(logging.Handler):  # Standard library logging handler to intercept root logging records
    """Route stdlib + uvicorn log records into the structlog pipeline."""

    def emit(self, record: logging.LogRecord) -> None:  # Custom event emission handler
        structlog.get_logger(record.name).log(record.levelno, record.getMessage())  # Redirect standard log records into structlog pipeline


def _configure_stdlib_interception(level: int) -> None:  # Clear default logging handlers and inject InterceptHandler
    root = logging.getLogger()  # Retrieve root standard library logger
    root.handlers = [InterceptHandler()]  # Replace all root handlers with our InterceptHandler
    root.setLevel(level)  # Set root log level filter
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):  # Loop over standard uvicorn log targets
        lg = logging.getLogger(name)  # Get target logger instance
        lg.handlers = []  # Discard uvicorn's custom stdout logging handlers
        lg.propagate = True  # Enable propagation up to the root InterceptHandler


def _configure_loguru_sinks(settings: Settings, level: str) -> None:  # Configure Loguru outputs
    """Console + rotating file sinks (development). Mirrors the article setup."""
    loguru_logger.remove()  # Clear default Loguru stdout handlers to prevent duplicates
    console_fmt = (  # Define dev console log template format with colors
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan> | <level>{message}</level> | "
        "<dim>{extra[ctx]}</dim>"
    )
    loguru_logger.add(sys.stderr, format=console_fmt, level=level, colorize=True)  # Register console sink pointing to stderr

    log_dir = Path(settings.log_dir)  # Map logging directory target string to a Path object
    try:
        log_dir.mkdir(parents=True, exist_ok=True)  # Create logs directory if it does not exist
    except OSError:  # Catch filesystem permission/write failures
        return  # No writable log directory available -> fallback to console logging only

    file_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message} | {extra[ctx]}"  # Log format string for file targets
    loguru_logger.add(  # Add main file output sink for INFO levels and above
        log_dir / "app_{time:YYYY-MM-DD}.log",  # Set rotating log filename template
        rotation="100 MB",  # Rotate log file when size reaches 100MB
        retention="30 days",  # Keep historical log files up to 30 days
        compression="zip",  # Compress archived logs using zip
        level="INFO",  # Minimum severity level to store in this file
        format=file_fmt,  # Apply file format template
        enqueue=True,  # Enable thread-safe queuing for async log emission
    )
    loguru_logger.add(  # Add specialized file output sink for ERROR levels and above
        log_dir / "errors_{time:YYYY-MM-DD}.log",  # Set rotating error filename template
        rotation="50 MB",  # Rotate error log file when size reaches 50MB
        retention="60 days",  # Keep historical error logs up to 60 days
        level="ERROR",  # Minimum severity level to store (ERROR/CRITICAL)
        format=file_fmt,  # Apply file format template
        backtrace=True,  # Capture exception trace information
        diagnose=True,  # Intercept and append local variables inside call frames to traceback output
        enqueue=True,  # Enable thread-safe queueing
    )


def configure_logging(settings: Settings) -> None:  # Bootstrap logging configurations
    """Configure structlog + Loguru + stdlib interception for the environment."""
    level_name = settings.log_level.upper()  # Fetch configured log level name in uppercase
    level_int = _level_to_int(level_name)  # Convert level string to logging integer

    if settings.is_production:  # Check if env is production
        final_processors = [structlog.processors.JSONRenderer()]  # End pipeline with JSON format renderer
        logger_factory = _PrintLoggerFactory(file=sys.stdout)  # Setup factory to output directly to stdout stream
    else:  # Development environment configuration
        _configure_loguru_sinks(settings, level_name)  # Initialize Loguru console and file sinks
        final_processors = [_render_to_loguru]  # End pipeline with custom Loguru forwarding renderer
        logger_factory = _NoopLoggerFactory()  # Setup no-op factory since logs flow to Loguru

    structlog.configure(  # Configure global Structlog options
        processors=_SHARED_PROCESSORS + final_processors,  # Bind shared pipeline processors plus final renderer
        wrapper_class=structlog.make_filtering_bound_logger(level_int),  # Set minimum log level filtering wrapper
        logger_factory=logger_factory,  # Bind the environment logger factory
        cache_logger_on_first_use=False,  # Disable logger caching to allow dynamic reconfiguration in testing
    )

    _configure_stdlib_interception(level_int)  # Intercept and route standard logs into the structlog pipeline

