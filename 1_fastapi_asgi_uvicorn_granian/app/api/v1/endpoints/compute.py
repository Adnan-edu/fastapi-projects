from fastapi import APIRouter

from app.services import compute as compute_service

router = APIRouter(prefix="/compute", tags=["compute"])


@router.get("/light")
def light_compute(n: int = 10000):
    return compute_service.light_compute(n)


@router.get("/io-simulated")
async def io_simulated(delay: float = 0.5):
    return await compute_service.io_simulated(delay)