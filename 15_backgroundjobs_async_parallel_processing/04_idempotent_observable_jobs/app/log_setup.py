"""Structured (JSON) logging via structlog.

The module is named ``log_setup`` rather than ``logging`` so it doesn't
shadow the stdlib ``logging`` package when imported from inside ``app/``.
"""

from __future__ import annotations

import logging

import structlog

logging.basicConfig(level=logging.INFO, format="%(message)s")

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger()
