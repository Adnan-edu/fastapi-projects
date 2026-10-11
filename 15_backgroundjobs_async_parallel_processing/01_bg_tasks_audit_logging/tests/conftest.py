"""Shared pytest fixtures.

We set DATABASE_URL before app.db is imported (it reads the env at import
time) and swap the session dependency for a fake so tests never touch
Postgres.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)


@dataclass
class FakeRow:
    id: int
    order_id: int
    customer_id: int
    status: str
    amount: str


@dataclass
class FakeSession:
    """Records every executed statement and returns a canned row list."""

    rows: list[FakeRow] = field(default_factory=list)
    executed: list[Any] = field(default_factory=list)

    async def execute(self, stmt):
        self.executed.append(stmt)

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                class _S:
                    def __init__(self, rows):
                        self._rows = rows

                    def all(self):
                        return self._rows

                return _S(self._rows)

        return _Result(self.rows)


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def client(fake_session, tmp_path, monkeypatch):
    """TestClient with the DB session stubbed and audit.log redirected
    to a tmp file so tests don't write into the repo."""
    from app import audit
    from app.db import get_session
    from app.main import app

    monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.log")

    async def _fake_get_session():
        yield fake_session

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        with TestClient(app) as c:
            c.audit_file = audit.AUDIT_FILE  # type: ignore[attr-defined]
            yield c
    finally:
        app.dependency_overrides.clear()
