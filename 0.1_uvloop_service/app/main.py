import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ingest, process, monitor
from app.core.config import settings
from app.core.loop_inspector import get_loop_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    info = get_loop_info()
    if info.is_uvloop:
        logger.info(f"Active event loop: {info.loop_type}")
    else:
        logger.warning(f"Standard event loop detected: {info.loop_type}")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(ingest.router)
app.include_router(process.router)
app.include_router(monitor.router)
