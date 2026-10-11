"""Liveness and readiness probes.

There are two distinct questions a deployment platform asks:

- **Liveness ("are you alive?")** — answered by `/healthz`. If this returns
  non-200, the orchestrator restarts the pod. It must NOT depend on
  external services; otherwise a DB outage triggers a restart loop that
  makes the outage worse.

- **Readiness ("are you ready to serve traffic?")** — answered by `/readyz`.
  If this returns non-200, the orchestrator stops routing new traffic but
  does NOT restart. It SHOULD check downstream dependencies (here: the DB)
  because a service that can't reach its DB shouldn't receive requests.

Keeping the two endpoints distinct is what lets a platform like Kubernetes
do the right thing during a DB blip: stop sending traffic, but don't kill
healthy pods that would just come back up unhealthy.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

# A router groups related endpoints. Tags are used by the Swagger UI to
# group operations under a common heading.
router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Trivial liveness — the process is up and the event loop is turning.

    No DB call here, deliberately. If a slow DB caused this to fail, the
    orchestrator would restart the pod, which doesn't help (the next pod
    will also see a slow DB) and may actually mask the real problem.
    """
    return {"status": "ok"}


@router.get("/readyz", summary="DB readiness probe")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness — confirm we can actually reach the DB.

    `SELECT 1` is the standard cheapest query. It doesn't touch any user
    data, doesn't allocate, and round-trips in microseconds on a healthy
    connection. `session.execute(text(...))` is the SQLAlchemy 2.0 way to
    run raw SQL safely.

    The `Depends(get_session)` injection means FastAPI opens (and closes)
    one short session per probe — exactly the right resource shape for a
    health check.
    """
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
