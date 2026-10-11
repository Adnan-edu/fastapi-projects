"""FastAPI launcher for the multiprocessing Parquet export.

The API process does not do the CPU work itself — it dispatches a Pool in a
worker thread so the event loop stays free.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI

from app.parquet_export import OUT_ROOT, run_export_job

app = FastAPI(title="Project 3 — Multiprocessing Parquet export")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "out_root": str(OUT_ROOT)}


@app.post("/export/parquet")
async def export_parquet(workers: int = 4) -> dict:
    if workers < 1 or workers > 32:
        return {"error": "workers must be between 1 and 32"}
    results = await asyncio.to_thread(run_export_job, workers)
    total_rows = sum(r["rows"] for r in results)
    return {
        "workers": workers,
        "chunks": results,
        "total_rows": total_rows,
        "out_root": str(OUT_ROOT),
    }
