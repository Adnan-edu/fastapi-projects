import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.services.pipeline import generate_stream_items

router = APIRouter(prefix="/process", tags=["process"])


@router.get("/stream/{count}")
async def process_stream(count: int = 1000):
    async def event_generator():
        async for item in generate_stream_items(count):
            yield json.dumps(item) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
