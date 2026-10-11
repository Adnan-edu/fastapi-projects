from fastapi import APIRouter

from app.api.v1.endpoints import compute, items

router = APIRouter(prefix="/api/v1")

router.include_router(items.router)
router.include_router(compute.router)