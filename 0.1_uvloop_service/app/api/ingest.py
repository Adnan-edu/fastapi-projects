from fastapi import APIRouter
from typing import List
from app.services.pipeline import process_batch

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/batch")
async def ingest_batch(items: List[dict]):
    results = await process_batch(items)
    return {"processed": len(results), "results": results}
