"""Lightweight audit-log writer for `BackgroundTasks`.

A single append, no CPU work, no large memory — safe to run in the same
worker process after the response is sent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# Anchor the log file next to the project root so its location does not
# depend on the directory uvicorn was launched from.
AUDIT_FILE = Path(__file__).resolve().parent.parent / "audit.log"


def write_audit_log(user_id: int, path: str, query: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with AUDIT_FILE.open("a") as f:
        f.write(f"{ts}\tuser={user_id}\tpath={path}\tquery={query}\n")
