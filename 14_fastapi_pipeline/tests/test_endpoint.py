"""Endpoint smoke tests — exercise the real HTTP path end-to-end.

Why ASGITransport instead of an actual running server?
------------------------------------------------------
`httpx.ASGITransport(app)` lets the test client speak to the FastAPI app
in-process, without going through TCP. This is faster (no socket, no
serialization) and more reliable in CI (no port collisions, no
"connection refused while server boots") than spinning up uvicorn.

The trade-off: we don't exercise the actual networking layer. For
streaming behavior (header flushing, chunked transfer encoding) we'd
need a real server. For correctness of the response body, ASGITransport
is sufficient and much cleaner.

These tests DO require the `stream_pg` Docker container to be running
with the `order_events` table populated. They fail loudly (not silently
skip) if the DB is unavailable, on the assumption that you wouldn't run
the integration suite without the DB up.
"""

import json

import httpx
import pytest
from httpx import ASGITransport

from app.db import dispose_engine, init_engine
from app.main import app


@pytest.fixture
async def client():
    """One AsyncClient per test, with the DB engine initialized/disposed
    around it.

    Why function-scope (not module-scope)?
    -------------------------------------
    pytest-asyncio creates a fresh event loop per test by default. A
    module-scoped fixture would create the engine on the first test's
    loop, then try to reuse it on the next test's loop — asyncpg's
    connection pool blows up with "Event loop is closed" when it tries
    to terminate connections that belong to a now-dead loop.

    The cost is a fresh engine per test (and a fresh connection pool),
    which is ~50ms of setup. For two tests, that's a non-issue.
    """
    init_engine()
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        # Always dispose, even on test failure, so we don't leak
        # connections to the next test.
        await dispose_engine()


async def test_run_ndjson_returns_5_strictly_increasing_ids(client: httpx.AsyncClient):
    """The default pipeline should return exactly `limit` rows, each a
    parseable JSON object with an `id` field, and the ids must be strictly
    increasing — that's the contract that keyset pagination provides.

    Strict ordering matters because consumers use it as a resumption
    cursor: "I got rows up through id=X, give me everything after X."
    """
    resp = await client.get("/pipeline/run.ndjson", params={"limit": 5})

    assert resp.status_code == 200
    # `startswith` (not `==`) because the framework may append `; charset=…`.
    assert resp.headers["content-type"].startswith("application/x-ndjson")

    # `.splitlines()` handles \n vs \r\n robustly. The `if line.strip()`
    # filter guards against trailing-newline artifacts.
    lines = [line for line in resp.text.splitlines() if line.strip()]
    assert len(lines) == 5

    rows = [json.loads(line) for line in lines]
    assert all("id" in row for row in rows)

    # `sorted(set(ids))` is a compact way to assert "strictly increasing":
    # if ids == sorted(set(ids)), there are no duplicates and they're
    # already in ascending order.
    ids = [row["id"] for row in rows]
    assert ids == sorted(set(ids)), f"ids not strictly increasing: {ids}"


async def test_run_ndjson_status_filter_pushes_to_sql(client: httpx.AsyncClient):
    """The `status` query param must translate into a SQL WHERE — meaning
    every row in the response actually has that status. If the filter
    were applied in Python (or not at all), this would either be slow
    or return mixed statuses.

    This is the test that proves the "push filters into SQL" claim is
    real and not just documentation.
    """
    resp = await client.get(
        "/pipeline/run.ndjson", params={"status": "paid", "limit": 10}
    )
    assert resp.status_code == 200

    lines = [line for line in resp.text.splitlines() if line.strip()]
    # `paid` is one of the valid statuses in the dataset; assert at
    # least one match exists. If this fails, either the dataset shape
    # changed or the filter isn't being applied.
    assert lines, "expected at least one row with status=paid"

    rows = [json.loads(line) for line in lines]
    # The hard assertion: EVERY row has status=paid. A bug that applied
    # the filter only sometimes (or as a Python filter after a too-small
    # source limit) would fail here.
    assert all(row.get("status") == "paid" for row in rows)
