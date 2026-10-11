"""Project 1 — FastAPI BackgroundTasks for post-response audit logging.

The list endpoint returns rows immediately; the audit-log write is
scheduled on the request's BackgroundTasks and runs after the response
has been sent.
"""

from __future__ import annotations

from fastapi import BackgroundTasks, Depends, FastAPI, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.db import get_session
from app.models import OrderEvent

app = FastAPI(title="Project 1 — BackgroundTasks audit")


@app.get("/orders")
async def list_orders(
    background_tasks: BackgroundTasks,
    customer_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(OrderEvent)
        .order_by(OrderEvent.created_at, OrderEvent.id)
        .limit(limit)
    )
    if customer_id is not None:
        stmt = stmt.where(OrderEvent.customer_id == customer_id)
    if status is not None:
        stmt = stmt.where(OrderEvent.status == status)

    rows = (await session.execute(stmt)).scalars().all()

    # Scheduled here, executed after FastAPI sends the response body.
    background_tasks.add_task(
        write_audit_log,
        user_id=42,
        path="/orders",
        query={"customer_id": customer_id, "status": status, "limit": limit},
    )

    return {
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "order_id": r.order_id,
                "status": r.status,
                "amount": str(r.amount),
            }
            for r in rows
        ],
    }
