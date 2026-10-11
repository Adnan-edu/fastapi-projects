import json
import logging
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def json_sink(message) -> None:
    record = message.record
    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "request_id": record["extra"].get("request_id", "-"),
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    if record["extra"]:
        for key, value in record["extra"].items():
            if key not in log_entry:
                log_entry[key] = value
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
            "traceback": record["exception"].traceback if record["exception"].traceback else None,
        }
    sys.stderr.write(json.dumps(log_entry, default=str) + "\n")


def setup_logging(json_output: bool = False) -> None:
    logger.remove()

    if json_output:
        logger.add(
            json_sink,
            level="DEBUG",
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "{extra[request_id]} | "
                "<level>{message}</level>"
            ),
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )

    logger.add(
        "logs/app.log",
        level="INFO",
        serialize=True,
        enqueue=True,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    logger.info("Logging initialized")