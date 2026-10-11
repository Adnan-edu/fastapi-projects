import os
from pathlib import Path

import psycopg
import pytest

DSN = os.environ.get(
    "PG_DSN",
    "postgresql://cursor:cursor@localhost:5432/cursor_pagination",
)


@pytest.fixture(scope="session")
def dsn() -> str:
    return DSN


@pytest.fixture(scope="session", autouse=True)
def _require_db(dsn: str) -> None:
    """Skip the whole module if the DB or order_events table is not ready."""
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM order_events")
            (n,) = cur.fetchone()
    except Exception as e:
        pytest.skip(f"DB not available: {e}", allow_module_level=True)
    if n < 1000:
        pytest.skip(f"order_events too small: {n} rows", allow_module_level=True)


@pytest.fixture()
def tmp_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "export"
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PARQUET_OUT_ROOT", str(out))
    monkeypatch.setenv("PG_DSN", DSN)
    return out
