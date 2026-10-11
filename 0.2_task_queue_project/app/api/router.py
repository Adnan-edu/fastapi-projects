# =====================================================================
# app/api/router.py - Aggregates every sub-router into ONE APIRouter
# =====================================================================
# PURPOSE
# -------
# FastAPI's `app.include_router(...)` only takes one router at a time.
# Rather than calling it five times in main.py, we build a single
# parent router here that includes all the domain routers. main.py
# then mounts THIS combined router under /api/v1.
# =====================================================================

from fastapi import APIRouter

# Each domain has its own router module under app/api/. We alias each
# imported `router` to a distinct local name so we can include them
# all without name collisions.
from app.api.users import router as users_router
from app.api.jobs import router as jobs_router
from app.api.reports import router as reports_router
from app.api.payments import router as payments_router
from app.api.webhooks import router as webhooks_router

# The single top-level APIRouter that main.py mounts.
router = APIRouter()

# Each include_router call merges in the routes (and their per-router
# prefixes like "/users", "/jobs") under the parent router.
router.include_router(users_router)
router.include_router(jobs_router)
router.include_router(reports_router)
router.include_router(payments_router)
router.include_router(webhooks_router)
