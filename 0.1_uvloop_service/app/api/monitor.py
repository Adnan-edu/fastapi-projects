from fastapi import APIRouter
from app.core.loop_inspector import get_loop_info

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/loop")
async def loop_metrics():
    info = get_loop_info()
    return {
        "loop_type": info.loop_type,
        "loop_module": info.loop_module,
        "is_uvloop": info.is_uvloop,
        "timestamp": info.timestamp,
    }
